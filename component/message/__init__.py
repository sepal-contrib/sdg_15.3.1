import os 
from pathlib import Path

from sepal_ui.translator import Translator

# select the target language
lang = 'en'
if 'CUSTOM_LANGUAGE' in os.environ:
    lang = os.environ['CUSTOM_LANGUAGE']
    
# create a simple namespace with all the messages 
ms = Translator(Path(__file__).parent, lang)