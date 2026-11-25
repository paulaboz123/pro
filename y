Expand-Archive -Force $HOME\Downloads\changed_files_120.zip .
git add README.md studio tests
git commit -m "Add SCORM extraction report and read documents inside packages"
git push

uv run -m studio scorm_report
