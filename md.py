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
}

def replace_quotes(text):
    """Convert standard quotes to Swiss Guillemets (« »)"""
    if not text: return ""
    # Opening quote: Quote preceded by space or start of line
    text = re.sub(r'(?:\^|\\textasciicircum{})(.*?)(?:\^|\\textasciicircum{})', 
                  r'\\textsuperscript{\1}', text)
    # Closing quote: Quote followed by space, punctuation or end of line
    text = re.sub(r'(?:_|\\_)(.*?)(?:_|\\_)', 
                  r'\\textsubscript{\1}', text)
    return text

def md_to_latex(text):
    """Convert markdown and emoticons to LaTeX icons and formatting"""
    if not text: return ""
    
    # Swiss Quotes
    text = replace_quotes(text)

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

def md_to_html(text):
    """Convert markdown and emoticons to HTML icons and en-dashes"""
    if not text: return ""

    # Emoticons to Hex-Entity
    for emo in sorted(EMOTICON_MAP.keys(), key=len, reverse=True):
        code = EMOTICON_MAP[emo]
        # re.sub versteht die Escapes wie \) korrekt
        text = re.sub(emo, f'<span class="ph-emo">&#x{code};</span>', text)

    # Swiss Quotes
    text = replace_quotes(text)

    # Double dash to en-dash (–)
    text = re.sub(r'(?<!-)--(?!-)', '&ndash;', text)
    
    # Units
    text = re.sub(r'(\d+)\s+(kg|g|ml|l)', r'\1&#x202F;\2', text)

    # Sub-/superscript
    text = re.sub(r'_(.*?)_', r'<sub>\1</sub>', text)
    text = re.sub(r'\^(.*?)\^', r'<sup>\1</sup>', text)
    # Standard Markdown
    return markdown.markdown(text, extensions=["extra"])