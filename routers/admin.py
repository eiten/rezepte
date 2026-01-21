# routers/admin.py
from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
import aiosqlite
from database import get_db_connection, get_user_context
from template_config import templates
from routers.auth import pwd_context

router = APIRouter(prefix="/admin", tags=["admin"])

@router.get("/categories", response_class=HTMLResponse)
async def manage_categories(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["is_admin"]:
        return RedirectResponse(url="/", status_code=303)

    async with db.execute("SELECT * FROM step_categories WHERE id > 1 ORDER BY label_de") as cursor:
        categories = await cursor.fetchall()
    
    return templates.TemplateResponse("admin_categories.html", {
        "request": request,
        "categories": categories,
        **user_ctx
    })

@router.post("/categories/update")
async def update_category(
    request: Request,
    id: int = Form(...),
    label_de: str = Form(...),
    html_color: str = Form(...),
    codepoint: str = Form(...),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["is_admin"]:
        raise HTTPException(status_code=403)

    await db.execute(
        "UPDATE step_categories SET label_de = ?, html_color = ?, codepoint = ? WHERE id = ?",
        (label_de, html_color, codepoint, id)
    )
    await db.commit()
    return RedirectResponse(url="/admin/categories", status_code=303)

@router.get("/users", response_class=HTMLResponse)
async def manage_users(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    
    if not user_ctx["is_admin"]:
        return RedirectResponse(url="/", status_code=303)
    
    # Nutzer laden (inklusive des neuen is_active Feldes)
    async with db.execute("SELECT id, username, display_name, role, is_active, email FROM users ORDER BY username") as cursor:
        users = await cursor.fetchall()
    
    return templates.TemplateResponse("admin_users.html", {
        "request": request,
        "users": users,
        **user_ctx
    })

@router.post("/users/update")
async def update_user(
    request: Request,
    user_id: int = Form(...),
    username: str = Form(...),
    display_name: str = Form(...),
    email: str = Form(None),
    new_password: str = Form(None),
    is_admin: bool = Form(False),
    is_active: bool = Form(False),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    user_ctx = await get_user_context(request, db)
    if not user_ctx["is_admin"]:
        raise HTTPException(status_code=403)

    role = "admin" if is_admin else "guest"
    active_val = 1 if is_active else 0

    # 1. Basis-Daten aktualisieren (inkl. Email und is_active)
    await db.execute(
        "UPDATE users SET username = ?, display_name = ?, email = ?, role = ?, is_active = ? WHERE id = ?",
        (username, display_name, email, role, active_val, user_id)
    )

    # 2. Passwort nur ändern, wenn ein neues eingegeben wurde
    if new_password and new_password.strip():
        hashed_password = pwd_context.hash(new_password)
        await db.execute("UPDATE users SET password_hash = ? WHERE id = ?", (hashed_password, user_id))

    await db.commit()
    redirect_url = request.url_for("manage_users")
    return RedirectResponse(url=redirect_url, status_code=303)

@router.post("/users/add")
async def add_user(
    request: Request,
    username: str = Form(...),
    display_name: str = Form(...),
    email: str = Form(None),
    password: str = Form(...),
    is_admin: bool = Form(False),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    user_ctx = await get_user_context(request, db)
    if not user_ctx["is_admin"]:
        raise HTTPException(status_code=403)

    role = "admin" if is_admin else "guest"
    hashed_password = pwd_context.hash(password)

    # Neue User werden standardmäßig mit is_active = 1 angelegt
    await db.execute(
        "INSERT INTO users (username, display_name, email, password_hash, role, is_active) VALUES (?, ?, ?, ?, ?, 1)",
        (username, display_name, email, hashed_password, role)
    )
    await db.commit()
    redirect_url = request.url_for("manage_users")
    return RedirectResponse(url=redirect_url, status_code=303)

# routers/admin.py

@router.get("/paths", response_class=HTMLResponse)
async def manage_paths(request: Request, db: aiosqlite.Connection = Depends(get_db_connection)):
    user_ctx = await get_user_context(request, db)
    if not user_ctx["is_admin"]:
        return RedirectResponse(url="/", status_code=303)

    # Alle Ordner holen
    async with db.execute("SELECT * FROM folders ORDER BY parent_id, name") as cursor:
        rows = await cursor.fetchall()
        folders = [dict(r) for r in rows]

    # Baum bauen (rekursiv oder per Referenz)
    folder_dict = {f['id']: {**f, 'children': []} for f in folders}
    root_nodes = []
    for f_id, f_data in folder_dict.items():
        if f_data['parent_id'] and f_data['parent_id'] in folder_dict:
            folder_dict[f_data['parent_id']]['children'].append(f_data)
        else:
            root_nodes.append(f_data)

    return templates.TemplateResponse("admin_paths.html", {
        "request": request,
        "folder_tree": root_nodes,
        "all_folders": folders, # Für Dropdowns beim Verschieben
        **user_ctx
    })

# routers/admin.py

@router.post("/paths/update")
async def update_path(
    request: Request,
    id: int = Form(...),
    name: str = Form(...),
    parent_id: str = Form(None), # String, da leere Option im HTML "" sendet
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    user_ctx = await get_user_context(request, db)
    if not user_ctx["is_admin"]:
        raise HTTPException(status_code=403)

    # Validierung: parent_id in int umwandeln oder None lassen
    p_id = int(parent_id) if parent_id and parent_id.isdigit() else None
    
    # Sicherheitscheck: Ein Ordner kann nicht sein eigenes Parent sein
    if p_id == id:
        p_id = None 

    await db.execute(
        "UPDATE folders SET name = ?, parent_id = ? WHERE id = ?",
        (name, p_id, id)
    )
    await db.commit()
    redirect_url = request.url_for("manage_paths")
    return RedirectResponse(url=redirect_url, status_code=303)

@router.post("/paths/add")
async def add_path(
    request: Request,
    name: str = Form(...),
    parent_id: str = Form(None),
    db: aiosqlite.Connection = Depends(get_db_connection)
):
    user_ctx = await get_user_context(request, db)
    if not user_ctx["is_admin"]:
        raise HTTPException(status_code=403)

    p_id = int(parent_id) if parent_id and parent_id.isdigit() and int(parent_id) > 0 else 1

    await db.execute(
        "INSERT INTO folders (name, parent_id) VALUES (?, ?)",
        (name, p_id)
    )
    await db.commit()
    redirect_url = request.url_for("manage_paths")
    return RedirectResponse(url=redirect_url, status_code=303)