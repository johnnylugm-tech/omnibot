import os

source_file = "03-development/src/app/core/paladin.py"
with open(source_file, "r") as f:
    lines = f.readlines()

def get_block(start, end=None):
    if end is None:
        return "".join(lines[start-1:])
    return "".join(lines[start-1:end-1])

imports = "".join(lines[27:44])  # imports and StrEnum class

sanitizer_content = "".join(lines[:211])
with open("03-development/src/app/core/paladin/sanitizer.py", "w") as f:
    f.write(sanitizer_content)

injection_defense_content = imports + get_block(212, 417)
with open("03-development/src/app/core/paladin/injection_defense.py", "w") as f:
    f.write(injection_defense_content)

classifier_content = imports + get_block(417, 694)
with open("03-development/src/app/core/paladin/classifier.py", "w") as f:
    f.write(classifier_content)

grounding_content = imports + get_block(694, 858)
with open("03-development/src/app/core/paladin/grounding.py", "w") as f:
    f.write(grounding_content)

pipeline_content = imports + "from app.core.paladin.sanitizer import InputSanitizer\n" + \
                   "from app.core.paladin.injection_defense import PromptInjectionDefense\n" + \
                   "from app.core.paladin.classifier import SemanticInjectionClassifier, ClassificationResult\n" + \
                   "from app.core.paladin.grounding import GroundingChecker\n" + \
                   get_block(858)
with open("03-development/src/app/core/paladin/pipeline.py", "w") as f:
    f.write(pipeline_content)

init_content = """from .pipeline import PALADINPipeline, ProcessResult
from .grounding import GroundingChecker, GroundingResult
from .classifier import SemanticInjectionClassifier, ClassificationResult
from .injection_defense import PromptInjectionDefense
from .sanitizer import InputSanitizer
"""
with open("03-development/src/app/core/paladin/__init__.py", "w") as f:
    f.write(init_content)

# Remove the old god object
os.remove(source_file)
print("Paladin successfully split.")
