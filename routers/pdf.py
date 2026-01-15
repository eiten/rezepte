import os
import subprocess
import jinja2
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
import aiosqlite
from database import get_db_connection, get_config
from datetime import datetime

router = APIRouter()
config = get_config()

# Set up specific Jinja environment for LaTeX to avoid syntax conflicts
# We use <% ... %> for logic and << ... >> for variables
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
    """
    Escapes special LaTeX characters in user input.
    """
    if not text:
        return ""
    replacements = {
        '\\': r'\textbackslash{}',
        '{': r'\{',
        '}': r'\}',
        '%': r'\%',
        '$': r'\$',
        '&': r'\&',
        '#': r'\#',
        '_': r'\_',
        '^': r'\textasciicircum{}',
        '~': r'\textasciitilde{}'
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text

def md_to_latex(text):
    """
    Simple converter from Markdown-like syntax to LaTeX.
    This should run AFTER escape_latex to prevent injection.
    """
    if not text:
        return ""
    
    # 1. Bold: **text** -> \textbf{text}
    # Note: We implement a very simple replacement logic here.
    # For robust parsing, regex or a library is better, but this suffices for recipes.
    import re
    
    # Bold
    text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)
    # Italic
    text = re.sub(r'\*(.*?)\*', r'\\textit{\1}', text)
    
    # Temperature: 200°C -> \qty{200}{\degreeCelsius}
    # Looks for number + °C
    text = re.sub(r'(\d+)\s*°C', r'\\qty{\1}{\\degreeCelsius}', text)
    
    return text

@router.get("/recipe/{recipe_id}/pdf")
async def get_pdf(recipe_id: int, db: aiosqlite.Connection = Depends(get_db_connection)):
    """
    Generates and serves the PDF. Implements caching based on timestamps.
    """
    
    # 1. Fetch data
    async with db.execute("SELECT *, updated_at FROM recipes WHERE id = ?", (recipe_id,)) as cursor:
        recipe = await cursor.fetchone()
    
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    # 2. Check cache
    pdf_filename = f"rezept_{recipe_id}.pdf"
    # Ensure cache directories exist (absolute paths)
    cache_dir = os.path.abspath(config['pdf_cache_dir'])
    pdf_dir = os.path.join(cache_dir, "pdf")
    build_dir = os.path.join(cache_dir, "build")
    
    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(build_dir, exist_ok=True)
    
    pdf_path = os.path.join(pdf_dir, pdf_filename)
    
    # Logic: Rebuild if file missing or DB entry is newer than file
    needs_rebuild = True
    if os.path.exists(pdf_path):
        file_mtime = os.path.getmtime(pdf_path)
        # Convert DB timestamp string to timestamp float
        # Default format in SQLite: "YYYY-MM-DD HH:MM:SS"
        try:
            db_mtime = datetime.strptime(recipe['updated_at'], "%Y-%m-%d %H:%M:%S").timestamp()
            if db_mtime < file_mtime:
                needs_rebuild = False
        except Exception as e:
            print(f"Timestamp parsing error: {e}, rebuilding...")
            needs_rebuild = True

    if needs_rebuild:
        print(f"--> Building PDF for recipe {recipe_id}...")
        
        # 3. Aggregate data for template
        async with db.execute("SELECT * FROM steps WHERE recipe_id = ? ORDER BY position", (recipe_id,)) as cursor:
            steps_raw = await cursor.fetchall()
        
        steps_data = []
        for step in steps_raw:
            s_dict = dict(step)
            
            # Prepare text (Escape -> MD to LaTeX)
            safe_text = escape_latex(s_dict['markdown_text'])
            s_dict['latex_text'] = md_to_latex(safe_text)
            
            # Fetch ingredients
            query = """
                SELECT i.*, u.symbol as unit_symbol, u.latex_code as unit_latex, u.type as unit_type
                FROM ingredients i 
                LEFT JOIN units u ON i.unit_id = u.id 
                WHERE step_id = ? 
                ORDER BY i.position
            """
            async with db.execute(query, (step["id"],)) as i_cursor:
                # Convert rows to dicts to allow modification
                ing_rows = await i_cursor.fetchall()
                ingredients = []
                for ing in ing_rows:
                    i_dict = dict(ing)
                    if i_dict['amount_min'] is not None:
                         # The :g formatter removes trailing zeros automatically
                        i_dict['amount_min'] = f"{i_dict['amount_min']:g}"
                    
                    if i_dict['amount_max'] is not None:
                        i_dict['amount_max'] = f"{i_dict['amount_max']:g}"
                    i_dict['item'] = escape_latex(i_dict['item'])
                    if i_dict['note']:
                        i_dict['note'] = escape_latex(i_dict['note'])
                    ingredients.append(i_dict)
                
                s_dict["ingredients"] = ingredients
            
            steps_data.append(s_dict)

        # 4. Render template
        template = latex_jinja_env.get_template('master.tex')
        tex_content = template.render(
            recipe=recipe,
            steps=steps_data,
            current_date=datetime.now().strftime("%d.%m.%Y")
        )
        
        # 5. Write .tex file
        tex_filename = f"rezept_{recipe_id}.tex"
        tex_path = os.path.join(build_dir, tex_filename)
        
        with open(tex_path, "w") as f:
            f.write(tex_content)
            
        # 6. Compile with latexmk
        # -pdf: generate pdf
        # -lualatex: use lualatex engine
        # -outdir: where to put the PDF
        # -interaction=nonstopmode: don't stop on errors
        cmd = [
            "latexmk",
            "-pdf",
            "-lualatex",
            "-interaction=nonstopmode",
            f"-output-directory={pdf_dir}",
            tex_path
        ]

        env = os.environ.copy()
        env['LC_ALL'] = 'C.UTF-8'
        env['LANG'] = 'C.UTF-8'        
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
        except subprocess.CalledProcessError as e:
            # Simple error handling for now
            print(f"LaTeX error: {e.stderr.decode()}")
            raise HTTPException(status_code=500, detail="PDF generation failed. Check server logs.")

    # 7. Serve file
    safe_filename = recipe['name'].replace(" ", "_").replace("/", "-").replace("\\", "-")
    
    return FileResponse(
        pdf_path, 
        media_type='application/pdf', 
        # "inline" tells the browser to try opening it instead of saving
        content_disposition_type='inline', 
        filename=f"{safe_filename}.pdf"
    )
