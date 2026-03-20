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
    """Triggers database setup automatically when FastAPI starts."""
    await clip_db_handler.setup_db()

@api.get("/files/pre-existing")
async def get_pre_existing_files_meta() -> List[PublicFileMeta]:
    """Returns metadata of all pre-existing files (not assigned to any slot).

    Returns:
        List[PublicFileMeta]: Metadata of all pre-existing files.
    """
    return await clip_db_handler.get_pre_existing_files_meta()


@api.get("/files/{slot}")
async def get_file_meta(slot: int) -> PublicFileMeta:
    """Returns metadata of the file in the given slot.

    Args:
        slot (int): Slot number. Must be one of {0, 1, 2}.

    Returns:
        PublicFileMeta: Metadata of the file in the slot, or 204 if slot is empty.

    Raises:
        HTTPException: 400 if slot is not in ALLOWED_SLOTS.
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
    """Downloads the file stored in the given slot.

    Args:
        slot (int): Slot number. Must be one of {0, 1, 2}.

    Returns:
        FileResponse: The file stored in the slot.

    Raises:
        HTTPException: 400 if slot is not in ALLOWED_SLOTS.
        HTTPException: 404 if no file exists in the slot.
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
        
                
@api.get("/files")
async def get_all_files_meta(with_pre_existing: bool = False) -> List[PublicFileMeta]:
    """Returns metadata of all files, optionally including pre-existing ones.

    Args:
        with_pre_existing (bool): If True, includes files with slot -1. Defaults to False.

    Returns:
        List[PublicFileMeta]: Metadata of all matching files.
    """
    return await clip_db_handler.get_all_files_meta(with_pre_existing)

async def add_file_to_taken_slot(uploaded_file: UploadFile, file_in_slot: FileMeta) -> PublicFileMeta:
    """Replaces the file currently in a slot with the uploaded file.

    Args:
        uploaded_file (UploadFile): The new file to upload.
        file_in_slot (FileMeta): Metadata of the existing file occupying the slot.

    Returns:
        PublicFileMeta: Metadata of the newly uploaded file.
    """
    # TODO: ask user if wants to replace
    return await replace_file(slot=file_in_slot.file_slot,
                        new_file=uploaded_file)


@api.post("/files")
async def upload_file(uploaded_file: UploadFile, slot: int) -> PublicFileMeta:
    """Uploads a file to the specified slot. Replaces existing file if slot is taken.

    Args:
        uploaded_file (UploadFile): The file to upload.
        slot (int): Slot number to upload into. Must be one of {0, 1, 2}.

    Returns:
        PublicFileMeta: Metadata of the uploaded file.

    Raises:
        HTTPException: 400 if slot is not in ALLOWED_SLOTS.
        HTTPException: 500 if the upload fails.
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
    """Replaces the file in the given slot with a new file.

    Args:
        slot (int): Slot number of the file to replace. Must be one of {0, 1, 2}.
        new_file (UploadFile): The new file to store in the slot.

    Returns:
        PublicFileMeta: Metadata of the newly uploaded file.

    Raises:
        HTTPException: 400 if slot is not in ALLOWED_SLOTS.
        HTTPException: 404 if no file exists in the slot.
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
    """Deletes the file in the given slot.

    Args:
        slot (int): Slot number of the file to delete. Must be one of {0, 1, 2}.

    Returns:
        PublicFileMeta: Metadata of the deleted file.

    Raises:
        HTTPException: 400 if slot is not in ALLOWED_SLOTS.
        HTTPException: 404 if no file exists in the slot.
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


class TextBody(BaseModel):
    """Request body for text save endpoints."""

    text: str


@api.get("/text")
async def get_text():
    """Returns the most recently saved textbox text.

    Returns:
        dict: ``{"text": str}`` with the current text, or 204 if no saves exist.
    """
    text = await clip_db_handler.get_last_save()
    if text is None:
        return Response(status_code=204)
    return {"text": text}


@api.post("/text")
async def save_text(body: TextBody):
    """Saves the given text to the textbox history.

    Only saves if the text differs from the most recent save.

    Args:
        body (TextBody): Request body containing the text to save.

    Returns:
        dict: ``{"text": str}`` with the saved text.
    """
    last = await clip_db_handler.get_last_save()
    if body.text == last:
        return {"text": last}
    await clip_db_handler.add_save_to_textbox(body.text)
    return {"text": body.text}


@api.post("/text/undo")
async def undo_text():
    """Reverts the textbox to the previous save.

    If no previous save exists, the current text is returned unchanged.

    Returns:
        dict: ``{"text": str}`` with the text after undo, or 204 if history is empty.
    """
    result = await clip_db_handler.textbox_ctrl_z()
    if result is None:
        current = await clip_db_handler.get_last_save()
        if current is None:
            return Response(status_code=204)
        return {"text": current}
    return {"text": result}