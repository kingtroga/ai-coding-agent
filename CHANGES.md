The application has been improved to allow users to organize and search their notes using tags.

**Files Touched:**
*   `app/models/note.model.js`
*   `app/controllers/note.controller.js`

**How the new feature works:**

1.  **Tagging Notes:**
    *   The `Note` schema in `app/models/note.model.js` now includes a `tags` field, which is an array of strings.
    *   When creating a new note (POST `/notes`) or updating an existing note (PUT `/notes/:noteId`), users can include a `tags` array in the request body. For example:
        
```json
        {
            "title": "My Meeting Notes",
            "content": "Discussed Q3 strategy.",
            "tags": ["work", "meeting", "strategy"]
        }
        ```

    *   If no `tags` are provided during creation, the field will default to an empty array. If no `tags` are provided during an update, the existing tags will remain unchanged (or be removed if an empty array is explicitly sent).

2.  **Searching Notes by Tag:**
    *   The `GET /notes` endpoint now supports an optional `tag` query parameter.
    *   To find all notes associated with a specific tag, users can make a request like:
        `GET /notes?tag=work`
    *   This will return all notes that have "work" present in their `tags` array.

**Assumptions and Trade-offs:**

*   **Single Tag Search:** The current implementation of `GET /notes?tag=<tag_name>` only supports searching for one tag at a time. To search for multiple tags (e.g., notes tagged with "work" AND "meeting"), the `findAll` method in `note.controller.js` would require more complexquery logic (e.g., using MongoDB's `$all` operator for an array of tags). For this request, I assumed a single tag search was sufficient given the scope.
*   **Case Sensitivity:** Tag searches are case-sensitive by default with MongoDB's exact match on array elements. If case-insensitive tag search is required, additional processing (e.g., converting tags to lowercase before saving and searching) would be necessary.
*   **No Tag Validation:** The system does not currently validate the format or content of tags (e.g., preventing special characters or ensuring a minimum length). This might be a future improvement.
*   **Backwards Compatibility:** Existing notes without a `tags` field will implicitly have an undefined `tags` field, which MongoDB handles gracefully as an empty array when performing searches. This ensures that existing functionality remains intact.