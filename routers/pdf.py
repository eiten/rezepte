import os
import subprocess
import jinja2
import tempfile
import shutil
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
import aiosqlite
from database import get_db_connection, get_config
from datetime import datetime

router = APIRouter()
config = get_config()

# --- Path logic to go one level up from 'routers/' ---
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(BASE_DIR, "latex_templates", "ttf", "") # Trailing slash is important!

# Setup Jinja2
latex_jinja_env = jinja2.Environment(
    loader=jinja2.FileSystemLoader('latex_templates'),
    block_start_string='<%',
    block_end_string='%>',
    variable_start_string='<<',
    variable_end_string='>>',
    comment_start_string='<#',
    comment_end_string='#>',
    trim_blocks=True,
    lstrip_blocks=True
)

def escape_latex(text):
    """Escape special LaTeX characters"""
    if not text: return ""
    replacements = {
        '\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '%': r'\%',
        '$': r'\$', '&': r'\&', '#': r'\#', '_': r'\_',
        '^': r'\textasciicircum{}', '~': r'\textasciitilde{}'
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text

def md_to_latex(text):
    """Convert basic markdown formatting to LaTeX"""
    if not text: return ""
    import re
    text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)  # Bold
    text = re.sub(r'\*(.*?)\*', r'\\textit{\1}', text)  # Italic
    text = re.sub(r'(\d+)\s*°C', r'\\qty{\1}{\\degreeCelsius}', text)  # Temperature
    return text

@router.get("/recipe/{recipe_id}/pdf")
async def get_pdf(recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    
    # Fetch recipe data
    async with db.execute("SELECT *, updated_at FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # Setup cache paths
    cache_dir = os.path.abspath(config['pdf_cache_dir'])
    pdf_dir = os.path.join(cache_dir, "pdf")
    debug_dir = os.path.join(cache_dir, "debug")
    os.makedirs(pdf_dir, exist_ok=True)

    target_pdf_path = os.path.join(pdf_dir, f"{recipe_id}.pdf")
    
    # Sanitize filename for download
    safe_name = recipe['name'].replace(" ", "_").replace("/", "-").replace("\\", "-")
    download_filename = f"{safe_name}.pdf"

    # Check if PDF needs rebuild (compare timestamps)
    needs_rebuild = True
    if os.path.exists(target_pdf_path):
        pdf_mtime = os.path.getmtime(target_pdf_path)
        try:
            db_mtime = datetime.strptime(recipe['updated_at'], "%Y-%m-%d %H:%M:%S").timestamp()
            template_path = os.path.join("latex_templates", "master.tex")
            template_mtime = os.path.getmtime(template_path)
            
            if (db_mtime < pdf_mtime) and (template_mtime < pdf_mtime):
                needs_rebuild = False
        except Exception:
            needs_rebuild = True

    if needs_rebuild:
        print(f"--> Building PDF for Recipe {recipe_id} ({recipe['name']})...")

        # Fetch custom unit definitions
        async with db.execute("SELECT symbol, latex_code FROM units WHERE type != 'si'") as cursor:
            custom_units = await cursor.fetchall()
        
        unit_defs = ""
        for u in custom_units:
            raw_code = u['latex_code'] if u['latex_code'] else u['symbol']
            cmd_name = "".join([c for c in raw_code if c.isalpha()])
            if not cmd_name: cmd_name = "UnitX"
            unit_defs += f"\\DeclareSIUnit\\{cmd_name}{{{u['symbol']}}}\n"

        # Fetch steps with category metadata
        query_steps = """
            SELECT s.*, c.codepoint, c.is_ingredients 
            FROM steps s
            LEFT JOIN step_categories c ON s.category_id = c.id
            WHERE s.recipe_id = ? 
            ORDER BY s.position
        """
        async with db.execute(query_steps, (recipe_id,)) as cursor:
            steps_raw = await cursor.fetchall()
        
        steps_data = []
        for step in steps_raw:
            s_dict = dict(step)
            s_dict['latex_text'] = md_to_latex(escape_latex(s_dict['markdown_text']))

            # Convert icon codepoint to integer
            if s_dict['codepoint']:
                 s_dict['latex_icon'] = int(s_dict['codepoint'], 16)
            else:
                 s_dict['latex_icon'] = None

            # Fetch ingredients
            query_ing = """
                SELECT i.*, u.symbol, u.latex_code
                FROM ingredients i 
                LEFT JOIN units u ON i.unit_id = u.id 
                WHERE step_id = ? ORDER BY i.position
            """
            async with db.execute(query_ing, (step["id"],)) as i_cursor:
                ing_rows = await i_cursor.fetchall()
                ingredients = []
                for ing in ing_rows:
                    i = dict(ing)
                    # Format amounts (strip trailing zeros)
                    if i['amount_min'] is not None: i['amount_min'] = f"{i['amount_min']:g}"
                    if i['amount_max'] is not None: i['amount_max'] = f"{i['amount_max']:g}"
                    
                    i['item'] = escape_latex(i['item'])
                    if i['note']: i['note'] = escape_latex(i['note'])
                    
                    # Determine unit command for LaTeX
                    if i['latex_code']:
                        # Fall 1: Perfekter Latex Code aus DB (z.B. \gram)
                        i['unit_cmd'] = i['latex_code']
                    elif i['symbol']:
                        # Fall 2: Kein Latex Code, aber ein Symbol (z.B. "mg") -> Wir basteln "\mg"
                        clean_sym = "".join([c for c in i['symbol'] if c.isalpha()])
                        if not clean_sym: 
                            clean_sym = "UnitX" # Fallback für Symbole ohne Buchstaben
                        i['unit_cmd'] = f"\\{clean_sym}"
                    else:
                        # Fall 3: Gar keine Einheit (z.B. "3 Eier" ohne 'Stk' Auswahl)
                        i['unit_cmd'] = ""

                    ingredients.append(i)
                s_dict["ingredients"] = ingredients
            steps_data.append(s_dict)

        # Format metadata dates
        try:
            dt_update = datetime.strptime(recipe['updated_at'], "%Y-%m-%d %H:%M:%S")
            fmt_version_date = dt_update.strftime("%d.%m.%Y")
        except:
            fmt_version_date = "Unknown"
            
        fmt_print_date = datetime.now().strftime("%d.%m.%Y")
        
        # Escape optional fields
        src_text = escape_latex(recipe['source']) if recipe['source'] else None
        preamble_text = md_to_latex(escape_latex(recipe['preamble'])) if recipe['preamble'] else None

        # Render LaTeX template
        template = latex_jinja_env.get_template('master.tex')
        tex_content = template.render(
            recipe=recipe,
            preamble=preamble_text, # NEW
            steps=steps_data,
            unit_defs=unit_defs,
            date_version=fmt_version_date,
            date_print=fmt_print_date,
            FONT_PATH=FONT_PATH,
            source=src_text
        )

        # Build PDF in temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            tex_path = os.path.join(temp_dir, "recipe.tex")
            with open(tex_path, "w") as f:
                f.write(tex_content)
            
            # Save .tex file for debugging if enabled
            if config.get('debug', False):
                os.makedirs(debug_dir, exist_ok=True)
                shutil.copy2(tex_path, os.path.join(debug_dir, f"{recipe_id}.tex"))

            # Compile with latexmk
            cmd = [
                "latexmk", "-pdf", "-lualatex", "-interaction=nonstopmode",
                f"-output-directory={temp_dir}", tex_path
            ]
            env = os.environ.copy()
            env['LC_ALL'] = 'C.UTF-8'
            env['LANG'] = 'C.UTF-8'
            
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
            
            temp_pdf = os.path.join(temp_dir, "recipe.pdf")
            if not os.path.exists(temp_pdf):
                print(f"LaTeX Error:\n{result.stderr.decode()}")
                if config.get('debug', False):
                    try: shutil.copy2(os.path.join(temp_dir, "recipe.log"), os.path.join(debug_dir, f"{recipe_id}.log"))
                    except: pass
                raise HTTPException(status_code=500, detail="PDF Generation failed.")
                
            shutil.copy2(temp_pdf, target_pdf_path)

    return FileResponse(
        target_pdf_path, 
        media_type='application/pdf', 
        content_disposition_type='inline',
        filename=download_filename 
    )