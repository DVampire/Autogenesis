---
name: review_skill
description: Review a GitHub pull request. Use when asked to review a specific PR by number/URL. For reviewing the local working diff instead, use the code_review_skill.
version: 1.0.0
type: worker
license: N/A
category: code-quality
requirements: [cpu]
metadata: {}
---

# Review Skill (GitHub PR)

Review a GitHub pull request, applying the same correctness + cleanup analysis
as the code_review_skill but scoped to the PR's diff (not the local working tree).

## How to run (read first)

Tools: `bash_tool` to run `gh pr view`/`gh pr diff`, `read_file_tool`/`grep_search_tool`
for surrounding code. This is a **single-agent procedure**: gather the PR diff,
then run the multi-angle find/verify from the code_review_skill yourself over
that diff. Finish with `done_tool` (`result` = the findings list); if asked to
post comments, run `gh` via `bash_tool` first.

## No PR specified

If no PR number/URL was given, run `gh pr list` to show the open pull requests,
then ask the user which one to review.

## With a PR target

Review target: GitHub pull request `<number-or-url>`.

Gather the target's diff with the following (instead of any local `git diff`):

1. `gh pr view <number> --json title,body,author,baseRefName,headRefName,state,additions,deletions,changedFiles,labels` for context
2. `gh pr diff <number>` for the unified diff

The PR's diff is the only review scope — local working-tree changes are out of
scope. When an angle needs surrounding code, Read the files in this checkout if
it matches the PR's branch; otherwise fetch file contents via `gh`.

## Then review

Run the full multi-angle review process described in the code_review_skill
(Phase 1 find candidates across correctness + cleanup angles → Phase 2 verify
3-state → optional sweep) yourself, over the PR diff gathered above. Produce the
same ranked findings output.

If the user asked, post each confirmed finding as an inline PR comment via
`gh`; otherwise return the findings list. Finish with `done_tool`.
