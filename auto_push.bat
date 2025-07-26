@echo off
echo Adding all changes...
git add .

echo Committing with message: "Auto push"...
git commit -m "Auto push"

echo Pushing to remote...
git push

echo Done.
pause
