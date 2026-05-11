from fastapi import FastAPI, HTTPException, File, UploadFile, Request
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from enum import IntEnum
from pydantic import BaseModel,Field
import clip_db_handler
from clip_db_handler import FileMeta, PublicFileMeta
from fastapi.responses import FileResponse
from fastapi import Response
import logging
import constants

ALLOWED_SLOTS = constants.ALLOWED_SLOTS
PRE_EXISTING_FILES_SLOT = constants.PRE_EXISTING_FILES_SLOT
logging.basicConfig(level=logging.INFO, filemode="w", filename=constants.API_LOG_FILE_PATH,
                    format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger(__name__)
api = FastAPI()

# [ADDED] CORS middleware — required for browser-based clients (Flutter web,
# curl from a browser extension, etc.). Without this the browser blocks every
# cross-origin request before it even reaches our route handlers.
#
# allow_origins=["*"] is fine for local dev; tighten this to the Flutter web
# app's specific origin before deploying to the Pi.
api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@api.on_event("startup")
async def initialize_system():
    """Triggers database setup automatically when FastAPI starts."""
    await clip_db_handler.setup_db()
    log.info("system initialized successfully")

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
    # DEBUG: trace every incoming request. Useful in dev to confirm the route
    # receives the right value. Too noisy for INFO in production.
    log.debug("GET /files/%d — fetching slot metadata", slot)

    if slot not in ALLOWED_SLOTS:
        # WARNING: bad client input — expected in normal operation, not a bug.
        # Use WARNING (not ERROR) for 4xx: the server did nothing wrong.
        log.warning("invalid slot requested: %d (allowed: %s)", slot, ALLOWED_SLOTS)
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")

    to_ret = await clip_db_handler.get_file_meta_in_slot(slot)
    if to_ret:
        # DEBUG: normal success path — too noisy for INFO in production.
        log.debug("slot %d — returning metadata for '%s'", slot, to_ret.file_name)
        return to_ret
    else:
        # DEBUG: empty slot is a valid state, not an error.
        log.debug("slot %d is empty — returning 204", slot)
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
    log.debug("GET /files/%d/download - fetching slot file data", slot)
    if slot not in ALLOWED_SLOTS:
        log.warning("invalid slot requested: %d (allowed: %s)", slot, ALLOWED_SLOTS)
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")
    file_meta = await clip_db_handler.get_file_meta_in_slot(slot)
    if file_meta:
        log.debug("slot %d returning filedata for %s", slot, file_meta.file_name)
        file_response = FileResponse(path=file_meta.file_path,
                                    filename=file_meta.file_name,
                                    media_type=file_meta.file_type)
        return file_response
    else:
        # file_meta is None == file not found
        log.warning("file in slot %d not found — returning 404", slot)
        raise HTTPException(status_code=404, detail="file not found")
        
                
@api.get("/files")
async def get_all_files_meta(with_pre_existing: bool = False) -> List[PublicFileMeta]:
    """Returns metadata of all files, optionally including pre-existing ones.

    Args:
        with_pre_existing (bool): If True, includes files with slot -1. Defaults to False.

    Returns:
        List[PublicFileMeta]: Metadata of all matching files.
    """
    log.debug("GET /files - fetching all files meta. with pre existing files: %d", with_pre_existing)
    return await clip_db_handler.get_all_files_meta(with_pre_existing)


@api.post("/files")
async def upload_file(uploaded_file: UploadFile, slot: int) -> PublicFileMeta:
    """Uploads a file to the specified slot.

    Args:
        uploaded_file (UploadFile): The file to upload.
        slot (int): Slot number to upload into. Must be one of {0, 1, 2}.

    Returns:
        PublicFileMeta: Metadata of the uploaded file.

    Raises:
        HTTPException: 400 if slot is not in ALLOWED_SLOTS.
        HTTPException: 409 if slot is taken.
        HTTPException: 500 if the upload fails.
    """
    log.debug("POST /files - uploading file: %s \nto slot %d", str(uploaded_file), slot)
    if slot not in ALLOWED_SLOTS:
        log.warning("invalid slot requested: %d (allowed: %s)", slot, ALLOWED_SLOTS)
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")
    file_in_slot = await clip_db_handler.get_file_meta_in_slot(slot)
    if file_in_slot:
        log.warning("slot %d is taken with file: %s, cannot add file", slot, file_in_slot.file_name)
        raise HTTPException(status_code=409, detail="slot is taken")
    else:
        uploaded_file_meta = await clip_db_handler.add_file(uploaded_file, slot)
        if uploaded_file_meta:
            log.debug("successfully uploaded file %s to slot %d", uploaded_file_meta.file_name, slot)
            return uploaded_file_meta
        else:
            log.error("upload of file %s to slot %d failed", str(uploaded_file), slot)
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
    log.debug("POST /files/%d/replace - replacing file in slot: %d \nwith file: %s", slot, slot, new_file)
    if slot not in ALLOWED_SLOTS:
        log.warning("invalid slot requested for replacement: %d (allowed: %s)", slot, ALLOWED_SLOTS)
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")
    added_file = await clip_db_handler.replace_file(slot,new_file)
    if not added_file:
        log.error("replacement of slot %d with file: %s failed", slot, new_file)
        raise HTTPException(status_code=500, detail="failed to replace file")
    else:
        log.debug("successfully replaced file in slot: %d \nwith file: %s", slot, new_file)
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
    log.debug("DELETE /files/%d - removing file in slot %d", slot, slot)
    if slot not in ALLOWED_SLOTS:
        log.warning("invalid slot requested for removal: %d (allowed: %s)", slot, ALLOWED_SLOTS)
        raise HTTPException(status_code=400, detail=f"slot {slot} not in allowed slots: {ALLOWED_SLOTS}")
    file_meta = await clip_db_handler.get_file_meta_in_slot(slot)
    if not file_meta:
        log.warning("no file to remove in slot %d", slot)
        raise HTTPException(status_code=404, detail="file not found")
    removed = await clip_db_handler.remove_file(file_meta.file_uuid)
    if removed:
        log.info("successfully removed file %s in slot %d", removed.file_name, slot)
        return removed
    else:
        log.warning("file in slot %d removal failed", slot)
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
    log.debug("GET /text - getting the current text in textbox")
    text = await clip_db_handler.get_last_save()
    if text is None:
        log.debug("no text for textbox, null")
        return Response(status_code=204)
    log.debug("returned text: %s", text)
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
    log.debug("POST /text - uploading text to db: %s", body.text)
    last = await clip_db_handler.get_last_save()
    if body.text == last:
        log.debug("latest text saved is already %s", body.text)
        return {"text": last}
    await clip_db_handler.add_save_to_textbox(body.text)
    log.info("successfully uploaded text to latest save: %s", body.text)
    return {"text": body.text}


@api.post("/text/undo")
async def undo_text():
    """Reverts the textbox to the previous save.

    If no previous save exists, the current text is returned unchanged.

    Returns:
        dict: ``{"text": str}`` with the text after undo, or 204 if history is empty.
    """
    log.debug("POST /text/undo - going back one save in textbox")
    result = await clip_db_handler.textbox_ctrl_z()
    if result is None:
        current = await clip_db_handler.get_last_save()
        if current is None:
            log.debug("no latest saved text, returning 204")
            return Response(status_code=204)
        return {"text": current}
    return {"text": result}

