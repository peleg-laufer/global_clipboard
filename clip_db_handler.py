# TODO: fix documentation
import os
from typing import List, Optional, Literal
from enum import IntEnum
from pydantic import BaseModel,Field
from fastapi import UploadFile
import uuid
from pymongo import AsyncMongoClient
import asyncio
import mimetypes

print("RUNNING FROM THIS EXACT FILE:")
print(os.path.abspath(__file__))

class PublicFileMeta(BaseModel):
    """
    safe info to send to client
    """
    file_name: str = Field(..., min_length=1, max_length=512, description="file name")
    file_type: str = Field(..., description="file type")
    file_size: int = Field(..., description="file size in bytes")
    file_uuid: str = Field(..., min_length=1, max_length=512, description="file unique id")
    file_slot: int = Field(..., description="serial number of file")
    

class FileMeta(PublicFileMeta):
    """
    PublicFileMeta with internal server info
    """
    file_path: str = Field(..., min_length=1, max_length=512, description="file path")
    

class IllegalSlotError(Exception):
    """
    raised when illegal slot given from client
    """
    pass

FILES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "files")
ALLOWED_SLOTS = {0,1,2}
PRE_EXISTING_FILES_SLOT = -1
CONNECTION_STRING = "mongodb://localhost:27017/"
client = AsyncMongoClient(CONNECTION_STRING)
db = client["clipboard_db"]
files_collection = db["files_meta"]


async def setup_db():
    # TODO: break into readable stuff
    """
    Verifies connection, creates folder, sets up indexes.
    fixes mismatch between folder and db: if on db and not folder - delete
                                        if on folder and not on db - add to db
    """
    print(f"setting up db")
    # create file dir
    if not os.path.exists(FILES_PATH):
        os.makedirs(FILES_PATH)

    # check db
    await client.admin.command("ping")
    print(f"    MongoDB connected")

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
            new_file_path = os.path.join(FILES_PATH, new_file_uuid + '.' + ext)
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
    """gets a specific file by uuid

    Args:
        uuid (str): uuid of file

    Returns:
        FileMeta: metadata of requested file
    """
    print(f"finding meta of uuid: {uuid}")
    doc = await files_collection.find_one({"file_uuid": uuid}, {"id_": 0})
    if doc:
        print(f"    found file: {FileMeta(**doc).file_name}")
        return PublicFileMeta(**FileMeta(**doc).model_dump())
    else:
        print(f"    no document matching uuid")
        return None

async def get_file_meta_in_slot(slot: int) -> FileMeta:
    """returns the meta of file in given slot

    Args:
        slot (int): slot of file. legal values: [0,1,2]

    Returns:
        FileMeta: _description_
    """
    print(f"finding FileMeta in slot: {slot}")
    if slot not in ALLOWED_SLOTS:
        raise IllegalSlotError(f"slot {slot} given is illegal value, not in allowed slots: {ALLOWED_SLOTS}")
    doc = await files_collection.find_one({"file_slot": slot}, {"id_": 0})
    if doc:
        print(f"    found file in slot: {FileMeta(**doc).file_name}")
        return FileMeta(**doc)
    else:
        print(f"    no file found")
        return None

async def get_file_path(uuid: str) -> str:
    """returns path of file

    Args:
        uuid (str): uuid of file

    Returns:
        str: path of file
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
    """returns all the files from a given index, if not given returns all

    Args:
        first_n (int, optional): index to start from. Defaults to 0.

    Returns:
        List[File]: a list of the files
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



async def add_file(uploaded_file: UploadFile, slot: int)  -> FileMeta:
    # TODO: add 3 slot logic. make slot 0-2 unique somehow. maybe change the non slot to none!
    """add a given file to the server

    Args:
        uploaded_file (UploadFile): the file to add 
        slot (int) [0,1,2]: the slot for file

    Returns:
        File: the file that was added, including id
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
    """replace a file on server

    Args:
        uuid (str): uuid of the soon to be replaced file
        new_file (UploadFile): file to upload intead

    Returns:
        FileMeta: metadata of new file on server. None if no file with uuid given
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
    """removes a file based on uuid

    Args:
        uuid (str): uuid of file to delete

    Raises:
        HTTPException: no file matching uuid given

    Returns:
        FileMeta: meta of file that was removed
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