import type { PromptRegistry } from "./registry.js";

export function registerPrompts(reg: PromptRegistry) {
  reg.register(
    {
      name: "summarize",
      description: "Summarize a given text",
      variables: [{ name: "text", description: "Input text", required: true }]
    },
    "Summarize the following text:\n\n{{text}}\n\nReturn a concise summary."
  );

  reg.register(
    {
      name: "system-instructions",
      description: "System instructions with persona",
      variables: [{ name: "persona", description: "assistant persona", required: false }]
    },
    "You are a helpful assistant. Persona: {{persona}}"
  );
}