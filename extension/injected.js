console.log("LeetCode AUTO: Injected script loaded (main world)");

// Wait for Monaco to be available
function waitForMonaco(callback, maxRetries = 50) {
  let retries = 0;
  const interval = setInterval(() => {
    retries++;
    if (typeof monaco !== "undefined" && monaco.editor && monaco.editor.getEditors().length > 0) {
      clearInterval(interval);
      callback();
    } else if (retries >= maxRetries) {
      clearInterval(interval);
      console.warn("LeetCode AUTO: Monaco editor not found after max retries");
    }
  }, 500);
}

function getEditor() {
  if (typeof monaco !== "undefined" && monaco.editor) {
    const editors = monaco.editor.getEditors();
    return editors.length > 0 ? editors[0] : null;
  }
  return null;
}

window.addEventListener("message", (event) => {
  if (event.data.type === "GET_EDITOR_VALUE") {
    try {
      const editor = getEditor();
      if (editor) {
        const value = editor.getValue();
        const language = editor.getModel() ? editor.getModel().getLanguageId() : "cpp";
        window.postMessage({ type: "EDITOR_VALUE_RETURN", value, language }, "*");
      } else {
        // Retry after a short delay
        waitForMonaco(() => {
          const editor = getEditor();
          const value = editor ? editor.getValue() : "";
          const language = editor && editor.getModel() ? editor.getModel().getLanguageId() : "cpp";
          window.postMessage({ type: "EDITOR_VALUE_RETURN", value, language }, "*");
        }, 10);
      }
    } catch (e) {
      console.error("LeetCode AUTO: Error getting editor value:", e);
      window.postMessage({ type: "EDITOR_VALUE_RETURN", value: "", language: "cpp" }, "*");
    }
  }

  if (event.data.type === "SET_EDITOR_VALUE") {
    try {
      const doSet = () => {
        const editor = getEditor();
        if (editor) {
          // Use executeEdits for proper undo/redo support
          const fullRange = editor.getModel().getFullModelRange();
          editor.executeEdits("leetcode-auto", [{
            range: fullRange,
            text: event.data.value
          }]);
          // Also trigger a format to clean up
          editor.getAction('editor.action.formatDocument')?.run();
          console.log("LeetCode AUTO: Code injected into Monaco editor.");
        } else {
          console.error("LeetCode AUTO: Editor not found for SET_EDITOR_VALUE");
        }
      };

      const editor = getEditor();
      if (editor) {
        doSet();
      } else {
        waitForMonaco(doSet, 10);
      }
    } catch (e) {
      console.error("LeetCode AUTO: Error setting editor value:", e);
    }
  }
});

console.log("LeetCode AUTO: Message listener registered");
