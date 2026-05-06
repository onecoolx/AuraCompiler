#!/bin/bash
cd /home/jipeng/AuraCompiler
rm -f _debug.sh
git add -A
GIT_EDITOR=true git commit --amend --no-edit
git --no-pager log --oneline -3
