git checkout main
git pull
Expand-Archive -Force $HOME\Downloads\changed_files_112.zip .
git add README.md studio tests
git status
git commit -m "Company files button and sources in videos"
git push

git pull
uv run --no-project python $HOME\Downloads\set_dev_image.py "WKLEJ_URI"
