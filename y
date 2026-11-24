git checkout main
git pull
Expand-Archive -Force $HOME\Downloads\changed_files_109.zip .
Expand-Archive -Force $HOME\Downloads\changed_files_110.zip .
git add README.md studio tests
git status
git commit -m "Clara's changes"
git push

git checkout main
git pull
Expand-Archive -Force $HOME\Downloads\changed_files_111.zip .
git add README.md studio tests
git status
git commit -m "Clara's changes and settings"
git push

git pull
uv run --no-project python $HOME\Downloads\set_dev_image.py "WKLEJ_URI"
