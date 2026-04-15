import os
from typing import List, Optional, Literal
from enum import IntEnum
from pydantic import BaseModel,Field
from fastapi import UploadFile
import uuid
from pymongo import AsyncMongoClient
import asyncio
import mimetypes
import constants

print("RUNNING FROM THIS EXACT FILE:")
print(os.path.abspath(__file__))

class PublicFileMeta(BaseModel):
    """File metadata safe to expose to clients.

    Attributes:
        file_name (str): Original filename (1-512 chars).
        file_type (str): MIME type of the file.
        file_size (int): File size in bytes.
        file_uuid (str): Unique identifier for the file (1-512 chars).
        file_slot (int): Slot the file is assigned to (-1 for pre-existing, 0-2 for slots).
    """
    file_name: str = Field(..., min_length=1, max_length=512, description="file name")
    file_type: str = Field(..., description="file type")
    file_size: int = Field(..., description="file size in bytes")
    file_uuid: str = Field(..., min_length=1, max_length=512, description="file unique id")
    file_slot: int = Field(..., description="serial number of file")
    

class FileMeta(PublicFileMeta):
    """File metadata including internal server path. Extends PublicFileMeta.

    Attributes:
        file_path (str): Absolute path to the file on the server (1-512 chars).
    """
    file_path: str = Field(..., min_length=1, max_length=512, description="file path")
    
class TextSave(BaseModel):
    """A single saved state of the textbox.

    Attributes:
        text (str): The saved text content (max 512 chars).
        position (int): Position in history, 0 is most recent (0-4).
    """

    text: str = Field(..., max_length=512, description="current text from textbox")
    position: int = Field(..., ge=0, le=4)

class IllegalSlotError(Exception):
    """Raised when an invalid slot number is provided."""

    pass

FILES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "files")
print("files path: ", FILES_PATH)
ALLOWED_SLOTS = constants.ALLOWED_SLOTS
PRE_EXISTING_FILES_SLOT = constants.PRE_EXISTING_FILES_SLOT
ALLOWED_TEXT_POSITIONS = constants.ALLOWED_TEXT_POSITIONS

CONNECTION_STRING = "mongodb://localhost:27017/"
client = AsyncMongoClient(CONNECTION_STRING)
db = client["clipboard_db"]
files_collection = db["files_meta"]
textbox_collection = db["textbox"]


async def setup_db():
    """Initializes the database and file system on server startup.

    Creates the files directory if missing, verifies the MongoDB connection,
    and delegates to collection-specific setup and validation functions.
    """
    print(f"setting up db")
    # create file dir
    if not os.path.exists(FILES_PATH):
        os.makedirs(FILES_PATH)
    # check db connection:
    await client.admin.command("ping")
    print(f"    MongoDB connected")
    # check and fix db:
    await files_collection_setup_and_validation()
    await textbox_collection_setup_and_validation()


async def textbox_collection_setup_and_validation():
    """Sets up and validates the textbox collection.

    Creates a unique index on the position field and repairs any
    position inconsistencies by calling fix_positions.
    """
    # making position unique index
    await textbox_collection.create_index("position", unique=True)
    # check all positions are valid and delete duplicates:
    await fix_positions()

async def fix_positions():
    """Repairs position values in the textbox collection.

    Sorts all saves by position, removes duplicates, then reassigns
    sequential positions starting from 0.

    Example:
        positions {2: "first", 3: "second", 3: "duplicate"}
        become    {0: "first", 1: "second"}
    """
    all_saves = await textbox_collection.find({}, {"_id": 0}).sort("position", 1).to_list()
    # deduplicate: keep first occurrence of each position
    seen_positions = set()
    deduped = []
    for save in all_saves:
        if save["position"] not in seen_positions:
            seen_positions.add(save["position"])
            deduped.append(save)
    # reinsert with sequential positions starting from 0
    await textbox_collection.delete_many({})
    for new_position, save in enumerate(deduped):
        save["position"] = new_position
        await textbox_collection.insert_one(save)

async def add_save_to_textbox(text: str):
    """Prepends a new text save at position 0, shifting existing saves down.

    Drops the oldest save if the total would exceed 5.

    Args:
        text (str): The current textbox content to save.
    """
    existing = await textbox_collection.find({}, {"_id": 0}).sort("position", 1).to_list()
    new_saves = [{"text": text, "position": 0}] + existing  # prepend new save
    new_saves = new_saves[:5]  # cap at 5, dropping the oldest
    await textbox_collection.delete_many({})
    for new_position, save in enumerate(new_saves):
        save["position"] = new_position
        await textbox_collection.insert_one(save)

async def get_last_save() -> str:
    """Returns the most recently saved textbox text (position 0).

    Returns:
        str | None: The text at position 0, or None if no saves exist.
    """
    doc = await textbox_collection.find_one({"position": 0}, {"_id": 0})
    if doc:
        return doc["text"]
    return None

async def textbox_ctrl_z() -> str:
    """Deletes the most recent save and returns the new current text.

    Removes the save at position 0, repairs positions, then returns
    the text now at position 0.

    Returns:
        str | None: The new most recent text after undo, or None if history is now empty.
    """
    await textbox_collection.delete_one({"position": 0})
    await fix_positions()
    return await get_last_save()


async def get_all_textbox_history() -> List[TextSave]:
    """Returns all saved textbox states ordered by position.

    Returns:
        List[TextSave]: All saved states, each with text and position fields.
    """
    cur = textbox_collection.find({}, {"_id": 0})
    text_saves_dict = await cur.to_list()
    saves_in_format = []
    for save in text_saves_dict:
        saves_in_format.append(TextSave(**save))
    return saves_in_format


async def files_collection_setup_and_validation():
    """Sets up and validates the files collection and local file storage.

    Creates a unique index on file_uuid, then reconciles the database
    against the files directory:

    - Files in the directory but missing from the DB are added.
    - Duplicate DB entries for the same path are cleaned up.
    - DB entries whose files no longer exist on disk are deleted.
    - Files with invalid or duplicate slot assignments are reassigned to slot -1.
    """
    # making uuid unique index
    await files_collection.create_index("file_uuid", unique=True)
    print(f"    Index created")

    # verify db and files in folder match, ignoring sub-folders
    files_in_folder = []
    for poss_file in os.listdir(FILES_PATH):
        poss_file_path = os.path.join(FILES_PATH, poss_file)
        if os.path.isfile(poss_file_path): # ignoring folders
            files_in_folder.append(poss_file)
    print(f"    files on folder:")
    for filename in files_in_folder:
        print(f"        {filename}")
    files_on_db = await get_all_files_meta(True)
    print(f"    files on db: ")
    for file_meta in files_on_db:
        print(f"        ", file_meta.file_name)
    
    # adding missing files in db:
    print("     adding missing files to db")
    for file_name in files_in_folder:
        print("         checking ", file_name)
        file_path = os.path.join(FILES_PATH, file_name)
        print("             path: ", file_path)
        matching_files_in_db = await files_collection.find({"file_path": file_path}).to_list(None)
        print("             db documents matching path: ")
        print("             ", matching_files_in_db)
        if len(matching_files_in_db) == 0:  # not on db
            # adding to db
            # finding mime type of file
            print("             no db documents matching file")
            file_mime_type = mimetypes.guess_type(file_name)[0]
            new_file_uuid = str(uuid.uuid4())
            # renaming file to uuid
            ext = os.path.splitext(file_name)[1]
            new_file_path = os.path.join(FILES_PATH, new_file_uuid + ext)
            os.rename(file_path, new_file_path)
            # constracting missing FileMeta
            missing_file_meta = FileMeta(file_name=file_name,
                                         file_type=str(file_mime_type),
                                         file_size=os.path.getsize(new_file_path),
                                         file_slot=PRE_EXISTING_FILES_SLOT, # not it any slot
                                         file_path=new_file_path,
                                         file_uuid=new_file_uuid)
            inserted_meta = await files_collection.insert_one(missing_file_meta.model_dump())
            print("             added ", inserted_meta, " to db")
        elif len(matching_files_in_db) >= 2:
            # delete duplicates
            for matching_file in matching_files_in_db[1:]:
                await files_collection.delete_one({"file_path": file_path})
    
    print(f"    deleting wrong metas in db")
    # deleting wrong metas:
    slots = {0: 0,
             1: 0,
             2: 0}
    for file_meta in files_on_db:
        if not os.path.exists(file_meta.file_path):
            print(f"        deleting ", file_meta.file_name, " from db")
            await remove_file(file_meta.file_uuid)
        elif (file_meta.file_slot not in ALLOWED_SLOTS) and file_meta.file_slot != PRE_EXISTING_FILES_SLOT:  # illegal slot
            query_filter = {'file_uuid' : file_meta.file_uuid}
            update_operation = { '$set' : 
                {'file_slot': PRE_EXISTING_FILES_SLOT}
            }
            result = await files_collection.update_one(query_filter, update_operation)
        else:
            if file_meta.file_slot == PRE_EXISTING_FILES_SLOT:
                continue
            slots[file_meta.file_slot] += 1
            if slots[file_meta.file_slot] >= 2:  # more than 1 file in slot
                query_filter = {'file_uuid' : file_meta.file_uuid}
                update_operation = { '$set' :
                    {'file_slot': PRE_EXISTING_FILES_SLOT}
                }
                result = await files_collection.update_one(query_filter, update_operation)



async def get_file_meta(uuid: str) -> PublicFileMeta:
    """Returns public metadata for a file identified by UUID.

    Args:
        uuid (str): The unique identifier of the file.

    Returns:
        PublicFileMeta | None: Metadata of the file, or None if not found.
    """
    print(f"finding meta of uuid: {uuid}")
    doc = await files_collection.find_one({"file_uuid": uuid}, {"_id": 0})
    if doc:
        print(f"    found file: {FileMeta(**doc).file_name}")
        return PublicFileMeta(**FileMeta(**doc).model_dump())
    else:
        print(f"    no document matching uuid")
        return None

async def get_file_meta_in_slot(slot: int) -> FileMeta:
    """Returns full metadata for the file occupying the given slot.

    Args:
        slot (int): Slot number. Must be one of {0, 1, 2}.

    Returns:
        FileMeta | None: Metadata of the file in the slot, or None if the slot is empty.

    Raises:
        IllegalSlotError: If slot is not in ALLOWED_SLOTS.
    """
    print(f"finding FileMeta in slot: {slot}")
    if slot not in ALLOWED_SLOTS:
        raise IllegalSlotError(f"slot {slot} given is illegal value, not in allowed slots: {ALLOWED_SLOTS}")
    doc = await files_collection.find_one({"file_slot": slot}, {"_id": 0})
    if doc:
        print(f"    found file in slot: {FileMeta(**doc).file_name}")
        return FileMeta(**doc)
    else:
        print(f"    no file found")
        return None

async def get_file_path(uuid: str) -> str:
    """Returns the local filesystem path of a file identified by UUID.

    Args:
        uuid (str): The unique identifier of the file.

    Returns:
        str | None: Absolute path to the file, or None if not found.
    """
    print(f"finding path of uuid: {uuid}")
    file_meta = await get_file_meta(uuid)
    if file_meta:
        print(f"    found path: {file_meta.file_path}")
        return file_meta.file_path
    else:
        print(f"    no path found")
        return None
        

async def get_all_files_meta(with_pre_existing: bool = False) -> List[FileMeta]:
    """Returns metadata for all files in the collection.

    Args:
        with_pre_existing (bool): If True, includes files with slot -1. Defaults to False.

    Returns:
        List[FileMeta]: Metadata of all matching files.
    """
    if with_pre_existing:
        print(f"getting all files meta including pre existing files")
        cursor = files_collection.find({},
                                    {"_id": 0})
        files_dict = await cursor.to_list()
        files_filemeta = []
        for file_dict in files_dict:
            files_filemeta.append(FileMeta(**file_dict))
            for file_meta in files_filemeta:
                print(f"    {file_meta}")
        return files_filemeta
    else:
        print(f"getting all files meta without pre existing files")
        cursor = files_collection.find({"file_slot": {"$ne": -1}},
                                    {"_id": 0})
        files_dict = await cursor.to_list()
        files_filemeta = []
        for file_dict in files_dict:
            files_filemeta.append(FileMeta(**file_dict))
            for file_meta in files_filemeta:
                print(f"    {file_meta}")
        return files_filemeta

async def get_pre_existing_files_meta() -> List[PublicFileMeta]:
    """Returns metadata of all pre-existing files (not assigned to any slot).

    Returns:
        List[PublicFileMeta]: Metadata of all files with slot -1.
    """
    print(f"getting pre-existing files meta")
    cursor = files_collection.find({"file_slot": PRE_EXISTING_FILES_SLOT}, {"_id": 0})
    files_dict = await cursor.to_list()
    files_filemeta = []
    for file_dict in files_dict:
        files_filemeta.append(PublicFileMeta(**FileMeta(**file_dict).model_dump()))
    for file_meta in files_filemeta:
        print(f"    {file_meta}")
    return files_filemeta

async def add_file(uploaded_file: UploadFile, slot: int) -> FileMeta:
    """Stores an uploaded file on disk and records its metadata in the DB.

    Args:
        uploaded_file (UploadFile): The file to store.
        slot (int): Slot number to assign. Must be one of {0, 1, 2}.

    Returns:
        FileMeta | None: Metadata of the stored file, or None if an error occurs.

    Raises:
        IllegalSlotError: If slot is not in ALLOWED_SLOTS or the slot is already taken.
    """
    print(f"adding file to slot: {slot}")
    print(f"file: {uploaded_file}")
    if slot not in ALLOWED_SLOTS:
        raise IllegalSlotError(f"slot {slot} given is illegal value, not in {ALLOWED_SLOTS}")
    file_in_slot = await get_file_meta_in_slot(slot)        
    if isinstance(file_in_slot, FileMeta):
        print(f"    file in slot {slot}: {file_in_slot.file_name}")
        raise IllegalSlotError(f"slot {slot} is taken by {file_in_slot.file_name}")
    else:
        print(f"    no file in slot")
    # setting up metadata:
    new_file_uuid = str(uuid.uuid4())
    ext = os.path.splitext(uploaded_file.filename)[1]
    new_file_path = os.path.join(FILES_PATH, new_file_uuid + ext)
    new_file_name = uploaded_file.filename
    new_file_size = uploaded_file.size
    new_file_type = uploaded_file.content_type
    new_file_metadata = FileMeta(file_name=new_file_name,
                                 file_type=new_file_type,
                                 file_size=new_file_size,
                                 file_slot=slot,
                                 file_path=new_file_path,
                                 file_uuid=new_file_uuid)
    print(f"    new file metadata: ", str(new_file_metadata))
    # writing into local file:
    try:
        print(f"    reading file content")
        file_content = uploaded_file.file.read()
        print(f"    writing new file on server in path: {new_file_metadata.file_path}")
        with open(new_file_path, "wb") as new_file:
            new_file.write(file_content)
        inserted_file = await files_collection.insert_one(new_file_metadata.model_dump())
        return new_file_metadata
    except Exception as e:
        print("error: ", e)


async def replace_file(slot: int, new_file: UploadFile) -> FileMeta:
    """Removes the existing file in a slot and stores a new one in its place.

    Args:
        slot (int): Slot number of the file to replace. Must be one of {0, 1, 2}.
        new_file (UploadFile): The new file to store in the slot.

    Returns:
        FileMeta | None: Metadata of the newly stored file, or None if the slot was empty.

    Raises:
        IllegalSlotError: If slot is not in ALLOWED_SLOTS.
    """
    print("replacing slot: ", slot, " and putting: ", new_file)
    if slot not in ALLOWED_SLOTS:
        raise IllegalSlotError(f"slot {slot} given is illegal value, not in {ALLOWED_SLOTS}")
    file_in_slot = await get_file_meta_in_slot(slot)
    removed = await remove_file(file_in_slot.file_uuid)
    print(f"    removed: ", removed)
    if removed:
        added_file = await add_file(uploaded_file=new_file, slot=int(removed['file_slot']))
        print(f"    added: ", added_file)
        return added_file
    else:
        return None
    
        
async def remove_file(uuid: str) -> FileMeta:
    """Deletes a file's DB record and removes it from disk.

    Args:
        uuid (str): The unique identifier of the file to delete.

    Returns:
        dict | None: The deleted document as a dict, or None if no file matched the UUID.
    """
    print(f"removing uuid: {uuid}")
    to_remove = await files_collection.find_one_and_delete({"file_uuid": uuid}, {"_id": 0})
    if to_remove:
        path_to_remove = to_remove["file_path"]
        print(f"    trying to remove path: ", path_to_remove)
        if os.path.exists(path_to_remove):
            os.remove(path_to_remove)
        else:
            print(f"    no file matching path saved in db: ", to_remove)
        return to_remove
    else:
        return None