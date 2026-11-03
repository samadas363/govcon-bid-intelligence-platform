from pathlib import Path
from importlib.metadata import version

print("sentence-transformers version:", version("sentence-transformers"))

cache_dir = Path.home() / ".cache" / "huggingface" / "hub"
print("\nHugging Face model cache:", cache_dir)

if cache_dir.exists():
    models = [
        path.name
        for path in cache_dir.iterdir()
        if path.is_dir() and "sentence-transformers" in path.name.lower()
    ]

    if models:
        print("\nPotentially relevant cached models:")
        for model in models:
            print("-", model)
    else:
        print("\nNo Sentence Transformers models found in the default cache.")
else:
    print("\nDefault Hugging Face cache directory does not exist.")
