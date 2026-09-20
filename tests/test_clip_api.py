from fastapi.testclient import TestClient

from clip_api import api
from constants import settings

# ---------------------------------------------------------------- text tests

def test_save_text_and_get_text(client):
    """Test adding text to the database and retrieving it."""
    # Add text
    text = "Hello, World!"
    response = client.post("/text", json={"text": text})
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == text

    # Get text
    response = client.get("/text")
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == text

def test_get_text_when_empty(client):
    """Test that an empty textbox history returns 204 and no body."""
    response = client.get("/text")
    assert response.status_code == 204
    assert response.content == b""

def test_save_text_and_undo(client):
    """Test adding text to the database and undoing it."""
    # Add text
    text1 = "Hello1!"
    text2 = "Hello2!"
    response = client.post("/text", json={"text": text1})
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == text1
    response = client.post("/text", json={"text": text2})
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == text2

    response = client.post("/text/undo")
    assert response.status_code == 200
    data = response.json()
    assert data["text"] == text1

def test_save_same_text_twice_is_a_no_op(client):
    """Test that saving the same text twice only creates one save."""
    text = "Hello, World!"
    response = client.post("/text", json={"text": text})
    assert response.status_code == 200
    response = client.post("/text", json={"text": text})
    assert response.status_code == 200
    assert response.json()["text"] == text

    # only one save exists, so a single undo empties the history
    response = client.post("/text/undo")
    assert response.status_code == 204

def test_undo_with_no_saves(client):
    """Test that undoing an empty textbox history returns 204."""
    response = client.post("/text/undo")
    assert response.status_code == 204
    assert response.content == b""

def test_text_history_is_capped_at_five_saves(client):
    """Test that only the 5 most recent saves are kept."""
    # 6 saves - the oldest one ("save0") should be dropped
    for i in range(6):
        response = client.post("/text", json={"text": f"save{i}"})
        assert response.status_code == 200

    # undo back through the 4 saves still in history
    for expected in ["save4", "save3", "save2", "save1"]:
        response = client.post("/text/undo")
        assert response.status_code == 200
        assert response.json()["text"] == expected

    # the 5th undo empties the history - "save0" was never there to fall back on
    response = client.post("/text/undo")
    assert response.status_code == 204

def test_save_text_too_long(client):
    """Test that text over the 512 character limit is rejected."""
    response = client.post("/text", json={"text": "a" * 513})
    assert response.status_code == 422


# --------------------------------------------------------------- file tests

def test_save_file_and_get_file(client, tmp_path):
    """Test adding a file to the database and retrieving it."""
    # Create a temporary file
    file_content = b"Hello, File!"
    temp_file_path = tmp_path / "test_file.txt"
    temp_file_path.write_bytes(file_content)
    slot = 1

    # Add file
    with open(temp_file_path, "rb") as f:
        response = client.post("/files",
                                params={"slot": slot},
                                files={"uploaded_file": ("test_file.txt", f, "text/plain")})
    assert response.status_code == 200
    data = response.json()
    assert data["file_uuid"]

    # Get file
    response = client.get(f"/files/{slot}/download")
    assert response.status_code == 200
    assert response.content == file_content

def test_get_file_meta(client):
    """Test that a slot returns the metadata of the file in it."""
    file_content = b"Hello, File!"
    slot = 0

    response = client.post("/files",
                           params={"slot": slot},
                           files={"uploaded_file": ("notes.txt", file_content, "text/plain")})
    assert response.status_code == 200

    response = client.get(f"/files/{slot}")
    assert response.status_code == 200
    data = response.json()
    assert data["file_name"] == "notes.txt"
    assert data["file_type"] == "text/plain"
    assert data["file_size"] == len(file_content)
    assert data["file_slot"] == slot
    # file_path is internal - PublicFileMeta must not leak it to clients
    assert "file_path" not in data

def test_get_file_meta_of_empty_slot(client):
    """Test that an empty slot returns 204 and no body."""
    response = client.get("/files/0")
    assert response.status_code == 204
    assert response.content == b""

def test_get_file_meta_of_illegal_slot(client):
    """Test that a slot outside the allowed slots returns 400."""
    response = client.get("/files/7")
    assert response.status_code == 400

def test_download_file_from_empty_slot(client):
    """Test that downloading from an empty slot returns 404."""
    response = client.get("/files/2/download")
    assert response.status_code == 404

def test_download_file_from_illegal_slot(client):
    """Test that downloading from an illegal slot returns 400."""
    response = client.get("/files/7/download")
    assert response.status_code == 400

def test_upload_file_to_taken_slot(client):
    """Test that uploading to a slot that already has a file returns 409."""
    slot = 1

    response = client.post("/files",
                           params={"slot": slot},
                           files={"uploaded_file": ("first.txt", b"first", "text/plain")})
    assert response.status_code == 200

    response = client.post("/files",
                           params={"slot": slot},
                           files={"uploaded_file": ("second.txt", b"second", "text/plain")})
    assert response.status_code == 409

    # the original file is untouched
    response = client.get(f"/files/{slot}/download")
    assert response.content == b"first"

def test_upload_file_to_illegal_slot(client):
    """Test that uploading to a slot outside the allowed slots returns 400."""
    response = client.post("/files",
                           params={"slot": 7},
                           files={"uploaded_file": ("notes.txt", b"data", "text/plain")})
    assert response.status_code == 400

def test_get_all_files_meta(client):
    """Test that all filled slots are returned, and empty ones are not."""
    # nothing uploaded yet
    response = client.get("/files")
    assert response.status_code == 200
    assert response.json() == []

    for slot in [0, 2]:
        response = client.post("/files",
                               params={"slot": slot},
                               files={"uploaded_file": (f"file{slot}.txt", b"data", "text/plain")})
        assert response.status_code == 200

    response = client.get("/files")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert sorted(file_meta["file_slot"] for file_meta in data) == [0, 2]

def test_replace_file(client):
    """Test that replacing a file swaps its contents and metadata."""
    slot = 1

    response = client.post("/files",
                           params={"slot": slot},
                           files={"uploaded_file": ("old.txt", b"old content", "text/plain")})
    assert response.status_code == 200
    old_uuid = response.json()["file_uuid"]

    response = client.put(f"/files/{slot}/replace",
                          files={"new_file": ("new.txt", b"new content", "text/plain")})
    assert response.status_code == 200
    data = response.json()
    assert data["file_name"] == "new.txt"
    assert data["file_slot"] == slot
    assert data["file_uuid"] != old_uuid

    # the slot now serves the new content
    response = client.get(f"/files/{slot}/download")
    assert response.status_code == 200
    assert response.content == b"new content"

def test_replace_file_in_empty_slot(client):
    """Test that replacing a file in an empty slot returns 404."""
    response = client.put("/files/0/replace",
                          files={"new_file": ("new.txt", b"new content", "text/plain")})
    assert response.status_code == 404

def test_replace_file_in_illegal_slot(client):
    """Test that replacing a file in an illegal slot returns 400."""
    response = client.put("/files/7/replace",
                          files={"new_file": ("new.txt", b"new content", "text/plain")})
    assert response.status_code == 400

def test_remove_file(client):
    """Test that removing a file empties its slot."""
    slot = 2

    response = client.post("/files",
                           params={"slot": slot},
                           files={"uploaded_file": ("notes.txt", b"data", "text/plain")})
    assert response.status_code == 200

    response = client.delete(f"/files/{slot}")
    assert response.status_code == 200
    assert response.json()["file_name"] == "notes.txt"

    # the slot is empty, and the file is gone from disk too
    response = client.get(f"/files/{slot}")
    assert response.status_code == 204
    response = client.get(f"/files/{slot}/download")
    assert response.status_code == 404

def test_remove_file_from_empty_slot(client):
    """Test that removing a file from an empty slot returns 404."""
    response = client.delete("/files/0")
    assert response.status_code == 404

def test_remove_file_from_illegal_slot(client):
    """Test that removing a file from an illegal slot returns 400."""
    response = client.delete("/files/7")
    assert response.status_code == 400


# ------------------------------------------------------- pre-existing files

def test_no_pre_existing_files_on_a_clean_start(client):
    """Test that a clean files folder has no pre-existing files."""
    response = client.get("/files/pre-existing")
    assert response.status_code == 200
    assert response.json() == []

def test_file_dropped_into_the_folder_becomes_pre_existing(client):
    """Test that startup adopts a file copied into the files folder by hand."""
    # write straight to disk, behind the API's back
    with open(f"{settings.FILES_PATH}/dropped.txt", "wb") as dropped_file:
        dropped_file.write(b"i was here first")

    # restarting the server re-runs the disk/DB reconciliation in setup_db.
    # `client` must not be used after this block - the restart rebinds the
    # mongo client to the new server's event loop.
    with TestClient(api) as restarted_client:
        response = restarted_client.get("/files/pre-existing")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["file_name"] == "dropped.txt"
        assert data[0]["file_slot"] == settings.PRE_EXISTING_FILES_SLOT

        # pre-existing files sit outside the slots, so /files skips them
        response = restarted_client.get("/files")
        assert response.json() == []
