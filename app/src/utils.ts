export const BASE = "http://localhost:8000";

/** Read a POST SSE stream, calling onEvent for each parsed event. Returns the last event. */
export async function consumeSSE(response: Response, onEvent: (data: any) => void): Promise<any> {
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastData: any = null;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop()!;
    for (const line of lines) {
      if (line.startsWith("data: ")) {
        const data = JSON.parse(line.slice(6));
        onEvent(data);
        lastData = data;
      }
    }
  }
  return lastData;
}
