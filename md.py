# md.py
import re
import markdown

# Central mapping of shortcuts to Phosphor hex codes
EMOTICON_MAP = {
    r':\)':  'E436', # Smiley
    r':\(':  'E43E', # Sad
    r';\)':  'E666', # Wink
    r'\(y\)': 'E48E', # Thumbs Up
    r'<3':    'E2A8', # Heart
    r'!!':    'E4E2', # Warning
    r'@@':    'E19A', # Clock
    r'!t':    'E5CC', # Thermometer
    r'PP':    'E4D6', # Users, People
}

# Global cache for unit_map from DB (loaded on first use)
_unit_map_cache = None

def load_unit_map(db_units: list = None) -> dict:
    """
    Load unit symbol -> latex code mapping from database units.
    
    Args:
        db_units: List of dicts or sqlite3.Row objects from DB with 'symbol' and 'latex_code' keys
    
    Returns:
        Dictionary mapping unit symbols to LaTeX codes
    """
    unit_map = {}
    
    if db_units:
        # Build map from database
        for unit in db_units:
            # Handle both dicts and sqlite3.Row objects
            if isinstance(unit, dict):
                symbol = unit.get('symbol')
                latex_code = unit.get('latex_code')
            else:
                # sqlite3.Row object - convert to dict
                unit_dict = dict(unit)
                symbol = unit_dict.get('symbol')
                latex_code = unit_dict.get('latex_code')
            
            if symbol and latex_code:
                unit_map[symbol.lower()] = latex_code
                unit_map[symbol] = latex_code  # Both lowercase and original
    
    # Fallback defaults (in case DB doesn't have these)
    defaults = {
        'g': r'\gram',
        'kg': r'\kilogram',
        'ml': r'\milli\liter',
        'l': r'\liter',
    }
    for k, v in defaults.items():
        if k not in unit_map:
            unit_map[k] = v
    
    return unit_map

def format_quantity(text: str, format: str = 'html', unit_map: dict = None) -> str:
    """
    Parse and format quantities like '[8g]', '[2.5-8.5 g]', '[8,5g]', '[4x6 cm]'.
    
    Normalizes decimal separators (both . and , accepted internally),
    outputs comma for HTML, comma for LaTeX (siunitx handles it with locale=DE).
    
    Supports:
    - Single: '8g' -> 8 g
    - Range: '2-8.5 g' -> 2–8,5 g
    - Multiplication: '4x6 cm' -> 4×6 cm
    
    Args:
        text: Content inside brackets, e.g. '8g', '2-8.5 g', '8,5ml', '4x6 cm'
        format: 'html' or 'latex'
        unit_map: Optional dict mapping unit symbols to LaTeX codes
    
    Returns:
        Formatted string for the target format, or original text if no match
    """
    if unit_map is None:
        unit_map = {}
    
    # Regex patterns
    # Pattern 1: "min[-max] unit" (range or single with optional whitespace)
    range_pattern = r'^(\d+[.,]\d+|\d+)\s*(?:-\s*(\d+[.,]\d+|\d+))?\s*([a-z°]+)$'
    # Pattern 2: "val1 x val2 unit" (multiplication)
    multi_pattern = r'^(\d+[.,]\d+|\d+)\s*[xX×]\s*(\d+[.,]\d+|\d+)\s*([a-z°]+)$'
    
    text_stripped = text.strip()
    
    # Try multiplication first
    match = re.match(multi_pattern, text_stripped, re.IGNORECASE)
    if match:
        val1_str, val2_str, unit_name = match.groups()
        
        # Normalize to comma
        val1_str = val1_str.replace('.', ',')
        val2_str = val2_str.replace('.', ',')
        
        unit_lower = unit_name.lower()
        unit_latex = unit_map.get(unit_lower, unit_name)
        
        if format == 'html':
            return f"{val1_str}&#x202F;×&#x202F;{val2_str}&#x202F;{unit_name}"
        elif format == 'latex':
            return f"{val1_str}\\,×\\,{val2_str}\\,{unit_latex}"
        return text
    
    # Try range/single
    match = re.match(range_pattern, text_stripped, re.IGNORECASE)
    if match:
        min_val_str, max_val_str, unit_name = match.groups()
        
        # Normalize to comma (German/Swiss format)
        min_val_str = min_val_str.replace('.', ',')
        if max_val_str:
            max_val_str = max_val_str.replace('.', ',')
        
        unit_lower = unit_name.lower()
        unit_latex = unit_map.get(unit_lower, unit_name)  # fallback to original if unknown
        
        if format == 'html':
            if max_val_str:
                return f"{min_val_str}&ndash;{max_val_str}&#x202F;{unit_name}"
            else:
                return f"{min_val_str}&#x202F;{unit_name}"
        elif format == 'latex':
            if max_val_str:
                return f"\\SIrange{{{min_val_str}}}{{{max_val_str}}}{{{unit_latex}}}"
            else:
                return f"\\SI{{{min_val_str}}}{{{unit_latex}}}"
    
    return text  # fallback: unprocessed

def format_ingredient_quantity(amount_min: float = None, amount_max: float = None, unit_symbol: str = None, format: str = 'html', unit_map: dict = None) -> str:
    """
    Format ingredient quantities from database fields.
    
    Converts float amounts to comma-separated strings and formats with unit.
    
    Args:
        amount_min: Minimum amount (float or None)
        amount_max: Maximum amount (float or None)
        unit_symbol: Unit symbol from DB (e.g. 'g', 'ml', 'EL')
        format: 'html' or 'latex'
        unit_map: Optional dict mapping unit symbols to LaTeX codes
    
    Returns:
        Formatted quantity string
    """
    if not unit_symbol:
        unit_symbol = ''
    
    if unit_map is None:
        unit_map = {}
    
    unit_latex = unit_map.get(unit_symbol, unit_symbol)  # fallback to original
    
    # Convert floats to comma-separated strings (using %g to remove trailing zeros)
    if amount_min is not None:
        min_str = ("%g" % amount_min).replace('.', ',')
    else:
        min_str = None
    
    if amount_max is not None:
        max_str = ("%g" % amount_max).replace('.', ',')
    else:
        max_str = None
    
    if format == 'html':
        if min_str and max_str:
            return f"{min_str}&ndash;{max_str}&#x202F;{unit_symbol}"
        elif min_str:
            return f"{min_str}&#x202F;{unit_symbol}"
        else:
            return unit_symbol
    elif format == 'latex':
        if min_str and max_str:
            return f"\\SIrange{{{min_str}}}{{{max_str}}}{{{unit_latex}}}"
        elif min_str:
            return f"\\SI{{{min_str}}}{{{unit_latex}}}"
        else:
            return unit_symbol
    
    return ""

def replace_quotes(text):
    """Convert standard quotes to appropriate format (enquote for LaTeX, guillemets for HTML)"""
    if not text: return ""
    # Opening quote: Quote preceded by space or start of line
    text = re.sub(r'(?:\^|\\textasciicircum{})(.*?)(?:\^|\\textasciicircum{})', 
                  r'\\textsuperscript{\1}', text)
    # Closing quote: Quote followed by space, punctuation or end of line
    text = re.sub(r'(?:_|\\_)(.*?)(?:_|\\_)', 
                  r'\\textsubscript{\1}', text)
    return text

def md_to_latex(text, unit_map: dict = None):
    """Convert markdown and emoticons to LaTeX icons and formatting"""
    if not text: return ""
    
    if unit_map is None:
        unit_map = {}
    
    # Parse and format quantities (before other replacements)
    text = re.sub(r'\[([^\]]+)\]', lambda m: format_quantity(m.group(1), 'latex', unit_map), text)
    
    # Convert quotes to \enquote{} for language-aware formatting
    text = re.sub(r'"([^"]+)"', r'\\enquote{\1}', text)

    # Trim and basic cleanup
    text = text.strip().replace('\r\n', '\n')

    for emo in sorted(EMOTICON_MAP.keys(), key=len, reverse=True):
        code = EMOTICON_MAP[emo]
        # Using a regex with word boundaries or space checks to avoid 
        # accidental replacements inside URLs etc.
        text = re.sub(emo, rf'\\picon{{{code}}}', text)

    # Basic Markdown (Bold, Italic, Units)
    text = re.sub(r'\*\*(.*?)\*\*', r'\\textbf{\1}', text)
    text = re.sub(r'\*(.*?)\*', r'\\textit{\1}', text)

    # Units & Dashes
    text = re.sub(r'(\d+)\s*°C', r'\\qty{\1}{\\degreeCelsius}', text)
    text = re.sub(r'(\d+)\s+(kg|g|ml|l)', r'\1\\,\2', text)
    #text = re.sub(r'(?<!-)\s*--\s*(?!-)', '--', text) # Ensure standalone double-dash, without surrounding spaces

    # Handle Newlines
    # \addlinespace is great because you are already using booktabs
    text = re.sub(r'\n\n+', r'\\addlinespace[0.5em] ', text)

    # Convert single newlines
    text = re.sub(r'\n', r'\\newline ', text)

    # Sub-/superscript
    text = re.sub(r'\^(.*?)\^', r'\\textsuperscript{\1}', text)
    text = re.sub(r'_(.*?)_', r'\\textsubscript{\1}', text)
    
    return text

def md_to_html(text, unit_map: dict = None):
    """Convert markdown and emoticons to HTML icons and en-dashes"""
    if not text: return ""
    
    if unit_map is None:
        unit_map = {}
    
    # Parse and format quantities (before other replacements)
    text = re.sub(r'\[([^\]]+)\]', lambda m: format_quantity(m.group(1), 'html', unit_map), text)

    # Swiss Quotes
    text = replace_quotes(text)

    # Trim and basic cleanup
    text = text.strip().replace('\r\n', '\n')
    # Double dash to en-dash (–)
    text = re.sub(r'(?<!-)--(?!-)', '&ndash;', text)

    # Emoticons to Hex-Entity
    for emo in sorted(EMOTICON_MAP.keys(), key=len, reverse=True):
        code = EMOTICON_MAP[emo]
        # re.sub versteht die Escapes wie \) korrekt
        text = re.sub(emo, f'<span class="ph-emo">&#x{code};</span>', text)

    # Units
    text = re.sub(r'(\d+)\s+(kg|g|ml|l)', r'\1&#x202F;\2', text)

    # Handle Newlines
    # Convert multiple newlines to spaced breaks
    text = re.sub(r'\n\n+', r'<br class="mb-3">', text)
    # Convert single newlines
    text = re.sub(r'\n', r'<br>', text)

    # Sub-/superscript
    text = re.sub(r'_(.*?)_', r'<sub>\1</sub>', text)
    text = re.sub(r'\^(.*?)\^', r'<sup>\1</sup>', text)
    # Standard Markdown
    return markdown.markdown(text, extensions=["extra"])
