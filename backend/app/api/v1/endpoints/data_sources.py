import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import encrypt_secret
from app.models.data_source import DataSource, DataSourceStatus, DataSourceType
from app.models.user import User
from app.schemas.data_source import DataSourceDBCreateRequest, DataSourceResponse
from app.services import db_sources

router = APIRouter()
settings = get_settings()


def _safe_filename(filename: str) -> str:
    return "".join(ch for ch in filename if ch.isalnum() or ch in (".", "_", "-")).strip("._")


@router.get("", response_model=list[DataSourceResponse])
def list_my_data_sources(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(DataSource)
        .filter(DataSource.user_id == current_user.id)
        .order_by(DataSource.created_at.desc())
        .all()
    )


@router.post("/upload", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
def upload_data_file(
    file: UploadFile = File(...),
    display_name: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    extension = Path(file.filename).suffix.lower()
    if extension not in settings.ALLOWED_UPLOAD_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file extension. Allowed: {settings.ALLOWED_UPLOAD_EXTENSIONS}",
        )

    user_upload_dir = settings.upload_dir_path / current_user.id
    user_upload_dir.mkdir(parents=True, exist_ok=True)

    sanitized = _safe_filename(file.filename or "upload")
    stored_filename = f"{uuid.uuid4()}_{sanitized}"
    stored_path = user_upload_dir / stored_filename

    with stored_path.open("wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    data_source = DataSource(
        user_id=current_user.id,
        source_type=DataSourceType.FILE,
        status=DataSourceStatus.ACTIVE,
        display_name=(display_name or file.filename or stored_filename).strip(),
        file_path=str(stored_path.resolve()),
        original_filename=file.filename,
        file_extension=extension,
        mime_type=file.content_type,
        file_size_bytes=stored_path.stat().st_size,
    )
    db.add(data_source)
    db.commit()
    db.refresh(data_source)
    return data_source


@router.get("/database-kinds")
def list_database_kinds():
    """The databases this server can actually reach, for the connection form.

    Driver availability is reported rather than assumed: offering an engine
    whose driver is not installed produces a connection that cannot be made.
    """
    return db_sources.catalogue()


@router.post("/db-connection/test")
def test_db_connection(
    payload: DataSourceDBCreateRequest,
    current_user: User = Depends(get_current_user),
):
    """Connect for real and report back, without storing anything."""
    return db_sources.probe(
        db_type=payload.db_type,
        host=payload.db_host,
        port=payload.db_port,
        database=payload.db_name,
        username=payload.db_username,
        password=payload.db_password,
    )


@router.post("/db-connection", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
def create_db_connection(
    payload: DataSourceDBCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Saved only once it has connected. A stored connection that was never
    # reached is a source the user believes in and the report cannot read.
    probe = db_sources.probe(
        db_type=payload.db_type,
        host=payload.db_host,
        port=payload.db_port,
        database=payload.db_name,
        username=payload.db_username,
        password=payload.db_password,
    )
    if not probe["ok"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not connect: {probe['error']}",
        )

    data_source = DataSource(
        user_id=current_user.id,
        source_type=DataSourceType.DB,
        status=DataSourceStatus.ACTIVE,
        display_name=payload.display_name.strip(),
        db_type=payload.db_type,
        db_host=payload.db_host,
        db_port=payload.db_port,
        db_name=payload.db_name,
        db_username=payload.db_username,
        db_password_encrypted=encrypt_secret(payload.db_password),
    )
    db.add(data_source)
    db.commit()
    db.refresh(data_source)
    return data_source


@router.get("/{data_source_id}/tables")
def list_source_tables(
    data_source_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The tables behind a database source, so a caller can choose one."""
    source = (
        db.query(DataSource)
        .filter(DataSource.id == data_source_id, DataSource.user_id == current_user.id)
        .first()
    )
    if source is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")
    if source.source_type != DataSourceType.DB:
        return []
    return [entry["table"] for entry in db_sources.tables_with_columns(source)]


@router.delete("/{data_source_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_data_source(
    data_source_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    data_source = (
        db.query(DataSource)
        .filter(DataSource.id == data_source_id, DataSource.user_id == current_user.id)
        .first()
    )
    if not data_source:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Data source not found")

    if data_source.source_type == DataSourceType.FILE and data_source.file_path:
        file_path = Path(data_source.file_path)
        if file_path.exists() and file_path.is_file():
            file_path.unlink(missing_ok=True)

    db.delete(data_source)
    db.commit()
    return None

