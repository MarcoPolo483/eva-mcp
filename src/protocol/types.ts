export type Json = string | number | boolean | null | Json[] | { [k: string]: Json };

export type JSONRPCRequest = {
  jsonrpc: "2.0";
  id?: number | string;
  method: string;
  params?: Json;
};

export type JSONRPCResponse = {
  jsonrpc: "2.0";
  id: number | string | null;
  result?: Json;
  error?: {
    code: number;
    message: string;
    data?: Json;
  };
};

// Minimal MCP shapes used by this server
export type ToolDef = {
  name: string;
  description?: string;
  inputSchema?: Json; // JSON Schema
};

export type ToolCallParams = { name: string; arguments?: Json };

export type ToolResult = {
  content: Array<{ type: "text"; text: string }>;
  isError?: boolean;
};

export type ResourceDef = {
  uri: string;
  name?: string;
  description?: string;
  mimeType?: string;
};

export type PromptDef = {
  name: string;
  description?: string;
  variables?: Array<{ name: string; description?: string; required?: boolean }>;
};