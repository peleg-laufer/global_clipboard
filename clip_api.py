# TODO:fix dcumentation
from fastapi import FastAPI, HTTPException, File, UploadFile, Request
from typing import List, Optional
from enum import IntEnum
from pydantic import BaseModel,Field
import clip_db_handler
from clip_db_handler import FileMeta, PublicFileMeta
from fastapi.responses import FileResponse
from fastapi import Response

ALLOWED_SLOTS = {0,1,2}
PRE_EXISTING_FILES_SLOT = -1
api = FastAPI()

@api.on_event("startup")
async def initialize_system():
    """
    Triggers the database setup automatically when FastAPI boots.
    """
    await clip_db_handler.setup_db()

@api.get("/files/{slot}")
async def get_file_meta(slot: int) -> PublicFileMeta:
    """get metadata of file from db

    Args:
        slot (int): 

    Raises:
        HTTPException: 400 if illegal slot

    Returns:
        FileMeta: metadata of file
    """
    if slot not in ALLOWED_SLOTS:
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")
    to_ret = await clip_db_handler.get_file_meta_in_slot(slot)
    if to_ret:
        return to_ret
    else:
        return Response(status_code=204)
    
@api.get("/files/{slot}/download")
async def get_file_data(slot: int) -> FileResponse:
    """get a file from db

    Args:
        uuid (str): uuid of file

    Raises:
        HTTPException: 404 file not found if no file on server with this uuid

    Returns:
        FileResponse: the wanted file
    """
    if slot not in ALLOWED_SLOTS:
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")
    file_meta = await clip_db_handler.get_file_meta_in_slot(slot)
    if file_meta:
        file_response = FileResponse(path=file_meta.file_path,
                                    filename=file_meta.file_name,
                                    media_type=file_meta.file_type)
        return file_response
    else:
        # file_meta is None == file not found
        raise HTTPException(status_code=404, detail="file not found")
        
                
@api.get("/files/pre-existing")
async def get_pre_existing_files_meta() -> List[PublicFileMeta]:
    """returns metadata of all pre-existing files (not assigned to any slot)

    Returns:
        List[PublicFileMeta]: metadata of all pre-existing files
    """
    return await clip_db_handler.get_pre_existing_files_meta()


@api.get("/files")
async def get_all_files_meta(with_pre_existing: bool = False) -> List[PublicFileMeta]:
    """returns all the metadata of files from a given index

    Args:
        first_n (int, optional): index to start from. Defaults to 0.

    Returns:
        List[FileMeta]: a list of the metadata of all files
    """
    return await clip_db_handler.get_all_files_meta(with_pre_existing)

async def add_file_to_taken_slot(uploaded_file: UploadFile, file_in_slot: FileMeta) -> PublicFileMeta:
    """makes sure user wants to replace
    replace

    Args:
        uploaded_file (UploadFile): file to upload
        file_in_slot (FileMeta): existing file

    Raises:
        HTTPException: 

    Returns:
        _type_: _description_
    """
    # TODO: ask user if wants to replace
    return await replace_file(slot=file_in_slot.file_slot,
                        new_file=uploaded_file)


@api.post("/files")
async def upload_file(uploaded_file: UploadFile, slot: int) -> PublicFileMeta:
    """upload a file to server

    Args:
        uploaded_file (UploadFile): the file needs to be upload

    Returns:
        FileMeta: the metadata of the stored file. None if no success
    """
    print("got file: " + str(uploaded_file))
    print(f"to enter to slot: {slot}")
    if slot not in ALLOWED_SLOTS:
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")
    file_in_slot = await clip_db_handler.get_file_meta_in_slot(slot)
    print(f"file in slot to replace: {file_in_slot}")
    if file_in_slot:
        return await add_file_to_taken_slot(uploaded_file=uploaded_file,
                                      file_in_slot=file_in_slot)
    else:
        uploaded_file_meta = await clip_db_handler.add_file(uploaded_file, slot)
        if uploaded_file_meta:
            return uploaded_file_meta
        else:
            raise HTTPException(status_code=500, detail="unable to upload file")
    

@api.put("/files/{slot}/replace")
async def replace_file(slot: int, new_file: UploadFile) -> PublicFileMeta:
    """
    replaces a file in the server
    Args:
        file_id (int): id of the file that needs to be replaced
        new_file (FileBase): the file to put in
    
    Raises:
        HTTPException: no file matching uuid given

    Returns:
        File: the file that was added, including id
    """
    if slot not in ALLOWED_SLOTS:
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")
    added_file = await clip_db_handler.replace_file(slot,new_file)
    if not added_file:
        print("file was not replaced")
        raise HTTPException(status_code=404, detail="file not found")
    else:
        return added_file
    
        
@api.delete("/files/{slot}")
async def remove_file(slot: int) -> PublicFileMeta:
    """deletes a file based on uuid

    Args:
        uuuid (str): uuid of file to delete

    Raises:
        HTTPException: no file matching uuid given

    Returns:
        FileMeta: metadata of file that was removed
    """
    if slot not in ALLOWED_SLOTS:
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")
    file_meta = await clip_db_handler.get_file_meta_in_slot(slot)
    if not file_meta:
        raise HTTPException(status_code=404, detail="file not found")
    removed = await clip_db_handler.remove_file(file_meta.file_uuid)
    if removed:
        return removed
    else:
        raise HTTPException(status_code=404, detail="file not found")