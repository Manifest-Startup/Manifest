---
name: manifest-ideas
description: "Create, find, edit, publish, import, export and qualify startup ideas in Manifest. Use when a person wants to capture a new idea, improve one, check if it's novel, run the idea-qualification interview, or move ideas in or out of Manifest."
---

# Ideas in Manifest

## Find and read
- `ideas` lists the person's ideas (newest first; `first`/`after` paginate). `idea` reads one in full.
- `universal_search` searches ideas, documents and people together; set `includeWeb` only when the person wants outside sources.
- `find_similar_ideas` checks novelty against existing ideas: use it before the person invests effort.
- `idea_owner` says who founded an idea; `check_idea_access` says whether the person can see or edit it and with what role.

## Create and change
- `create_idea` needs a title; a description makes everything downstream better. Ask for one if the person gave only a phrase.
- `update_idea` changes title, description or required skills.
- `delete_idea` is permanent (needs `confirm: true`). Suggest `export_ideas` first.
- `toggle_publish_idea` makes an idea public in discovery and pitch shorts, or hides it again (needs `confirm: true`; say who will see it).

## Qualification interview
Manifest interviews the founder to sharpen an idea before documents are generated.
1. `start_idea_qualification` with the person's rough idea text; it returns the first questions.
2. Ask the person those questions in your own words; don't invent answers. Send their answers with `continue_idea_qualification` (sessionId + userMessage). Each answer becomes a citable passage in the idea's knowledge graph, so after every answer sync the local vault (manifest-vault) if the person keeps one.
3. Repeat until the session reports it is complete; summarise the verdict.
- `my_idea_qualification_sessions` lists past interviews; `idea_qualification_session` reads one.

## Move ideas in and out
- `export_ideas` exports every idea as `json`, `csv` or `markdown`.
- `import_ideas` imports note exports and backups (fileContent, fileFormat, filename). Show the person what will be imported first.
