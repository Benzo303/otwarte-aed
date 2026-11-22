"""Uzupełnia nowe pliki referencyjne w istniejącym wolumenie bez nadpisywania danych."""
from pathlib import Path
import shutil
import uvicorn


def main():
    for filename in ('poland_boundary.json','locations.json'):
        source=Path('/app/seed')/filename
        target=Path(__file__).parent/'data/cache'/filename
        if source.exists() and not target.exists():
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(source,target)
    uvicorn.run("backend.main:app",host="0.0.0.0",port=8000)


if __name__=="__main__":main()
