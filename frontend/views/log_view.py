import streamlit as st
import streamlit.components.v1 as components

API_BASE_URL = "http://localhost:8000/api/agent"


def render_log_view():
  st.title("🔎 Log View — Vòng đời chatbot")
  st.caption(
      "Log mới được đẩy tới trình duyệt qua SSE; backend không cần polling."
  )
  components.html(
      f"""
      <!doctype html>
      <html>
        <head>
          <meta charset="utf-8">
          <style>
            :root {{ color-scheme: light; }}
            body {{ font-family: Inter, "Segoe UI", sans-serif; color: #172554;
                    background: #f5f8ff; margin: 0; }}
            .toolbar {{ display: flex; gap: 12px; align-items: center;
                        background: #fff; border: 1px solid #dbeafe;
                        border-radius: 14px; padding: 14px 18px;
                        box-shadow: 0 4px 16px #1e3a8a12; }}
            select {{ flex: 1; min-width: 0; padding: 10px 12px;
                      border: 1px solid #bfdbfe; border-radius: 9px;
                      background: #fff; color: #172554; }}
            #connection {{ color: #15803d; font-size: .9rem; }}
            #summary {{ display: grid;
                        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
                        gap: 12px; margin-top: 14px; }}
            .metric {{ background: linear-gradient(135deg,#fff,#eff6ff);
                       border: 1px solid #dbeafe; border-radius: 13px;
                       padding: 14px 18px; box-shadow: 0 4px 16px #1e3a8a0c; }}
            .metric-label {{ color: #64748b; font-size: .8rem;
                             text-transform: uppercase; letter-spacing: .04em; }}
            .metric-value {{ color: #1d4ed8; font-size: 1.2rem;
                             font-weight: 700; margin-top: 5px; }}
            #timeline {{ height: 620px; overflow-y: auto; margin-top: 14px;
                         padding-right: 5px; }}
            .event {{ position: relative; background: #fff;
                      border: 1px solid #dbeafe; border-left: 4px solid #60a5fa;
                      border-radius: 11px; padding: 14px 16px;
                      margin: 0 0 11px 4px;
                      box-shadow: 0 3px 12px #1e3a8a0b; }}
            .event.completed {{ border-left-color: #22c55e; }}
            .event.started {{ border-left-color: #f59e0b; }}
            .event.failed {{ border-left-color: #ef4444; }}
            .agent-group {{ margin-top: 16px; }}
            .agent-header {{ display: flex; flex-wrap: wrap; gap: 10px;
                             align-items: center; margin: 0 0 10px 4px; }}
            .agent-header h2 {{ margin: 0; color: #1e3a8a; font-size: 1.05rem; }}
            .agent-token {{ color: #475569; font-size: .85rem;
                            background: #e0f2fe; padding: 5px 10px;
                            border-radius: 999px; }}
            .event-heading {{ display: flex; flex-wrap: wrap; gap: 8px;
                              align-items: center; }}
            .event h3 {{ margin: 0; color: #1e40af; font-size: 1rem; }}
            .event-time {{ color: #64748b; font-size: .82rem; }}
            .badge {{ background: #eff6ff; color: #1d4ed8; padding: 3px 9px;
                      border-radius: 999px; font-size: .78rem; font-weight: 600; }}
            .event pre {{ white-space: pre-wrap; overflow-wrap: anywhere;
                          background: #f8fafc; color: #0f172a; padding: 11px;
                          border: 1px solid #e2e8f0; border-radius: 8px; }}
            .rag-chunks {{ display: grid; gap: 4px; padding-left: 20px;
                           list-style: none; }}
            .rag-chunk {{ color: #334155; }}
            details {{ margin-top: 8px; color: #475569; }}
            .error {{ color: #b91c1c !important; }}
            @media (max-width: 650px) {{
              #summary {{ grid-template-columns: 1fr; }}
              .toolbar {{ align-items: stretch; flex-direction: column; }}
            }}
          </style>
        </head>
        <body>
          <div class="toolbar">
            <select id="run-select" aria-label="Chọn lần chạy">
              <option value="">Đang tải log...</option>
            </select>
            <span id="connection">Đang kết nối tới EventBus...</span>
          </div>
          <div id="summary"></div>
          <div id="timeline"></div>
          <script>
            const apiBase = "{API_BASE_URL}";
            const runSelect = document.getElementById("run-select");
            const timeline = document.getElementById("timeline");
            const connection = document.getElementById("connection");
            const summary = document.getElementById("summary");
            const eventsByRun = new Map();
            const knownRuns = new Map();
            let selectedRun = "";
            let loadedRuns = false;

            function formatDate(value) {{
              if (!value) return "—";
              const date = new Date(value);
              if (Number.isNaN(date.getTime())) return value;
              return new Intl.DateTimeFormat("vi-VN", {{
                dateStyle: "medium",
                timeStyle: "medium",
              }}).format(date);
            }}

            function formatDuration(milliseconds) {{
              const safeMilliseconds = Math.max(0, milliseconds);
              if (safeMilliseconds < 1000) {{
                return `${{Math.floor(safeMilliseconds)}} mili giây`;
              }}
              const totalSeconds = Math.floor(safeMilliseconds / 1000);
              const hours = Math.floor(totalSeconds / 3600);
              const minutes = Math.floor((totalSeconds % 3600) / 60);
              const seconds = totalSeconds % 60;
              if (hours) return `${{hours}} giờ ${{minutes}} phút ${{seconds}} giây`;
              if (minutes) return `${{minutes}} phút ${{seconds}} giây`;
              return `${{seconds}} giây`;
            }}

            function statusLabel(status) {{
              const labels = {{
                running: "Đang chạy",
                started: "Bắt đầu",
                completed: "Hoàn tất",
                failed: "Thất bại",
              }};
              return labels[status] || status;
            }}

            function eventLabel(step) {{
              const labels = {{
                run: "Câu hỏi",
                router: "Phân loại câu hỏi",
                route: "Chọn nhánh xử lý",
                sql: "Luồng SQL",
                rag: "Xử lý RAG",
                table_retrieval: "Chọn bảng",
                join_resolution: "Dựng đường JOIN",
                sql_generation: "Sinh SQL",
                query_execution: "Thực thi truy vấn",
                rag_search: "Tìm kiếm tài liệu",
                synthesizer: "Tạo câu trả lời",
                evaluate_agent: "Đánh giá yêu cầu",
                sql_search_agent: "Tổng hợp dữ liệu SQL",
              }};
              return labels[step] || step;
            }}

            const agentLabels = {{
              orchestrator: "Điều phối",
              router: "Router Agent",
              sql_expert: "SQL Expert Agent",
              sql_executor: "SQL Executor Agent",
              rag_search: "RAG Search Agent",
              synthesizer: "Synthesizer Agent",
              evaluate_agent: "Evaluate Agent",
              sql_search_agent: "SQL Search Agent",
              other: "Agent khác",
            }};
            const stepAgents = {{
              run: "orchestrator",
              router: "router",
              route: "router",
              sql: "orchestrator",
              rag: "orchestrator",
              table_retrieval: "sql_expert",
              join_resolution: "sql_expert",
              sql_generation: "sql_expert",
              query_execution: "sql_executor",
              rag_search: "rag_search",
              synthesizer: "synthesizer",
              evaluate_agent: "evaluate_agent",
              sql_search_agent: "sql_search_agent",
            }};

            function agentKey(event) {{
              return event.agent || stepAgents[event.step] || "other";
            }}

            function formatTokens(value) {{
              return new Intl.NumberFormat("vi-VN").format(value || 0);
            }}

            function tokenTotals(events) {{
              const totals = {{ input_tokens: 0, output_tokens: 0, total_tokens: 0 }};
              let found = false;
              for (const event of events) {{
                const usage = event.details?.token_usage;
                if (!usage) continue;
                found = true;
                totals.input_tokens += Number(usage.input_tokens) || 0;
                totals.output_tokens += Number(usage.output_tokens) || 0;
                totals.total_tokens += Number(usage.total_tokens) || 0;
              }}
              return found ? totals : null;
            }}

            function getRunEvents(runId) {{
              if (!eventsByRun.has(runId)) {{
                eventsByRun.set(runId, new Map());
              }}
              return eventsByRun.get(runId);
            }}

            function updateRunOption(runId, event) {{
              const details = event.details || {{}};
              const run = knownRuns.get(runId) || {{}};
              if (details.question) run.question = details.question;
              if (!run.started_at) run.started_at = event.time;
              if (
                event.step === "run" &&
                (!event.event_id || event.event_id >= (run.last_event_id || 0))
              ) {{
                run.status = event.status;
                if (event.status === "completed" || event.status === "failed") {{
                  run.finished_at = event.time;
                }}
                if (event.event_id) run.last_event_id = event.event_id;
              }}
              knownRuns.set(runId, run);

              let option = Array.from(runSelect.options).find(
                (item) => item.value === runId
              );
              if (!option) {{
                option = document.createElement("option");
                option.value = runId;
                runSelect.appendChild(option);
              }}
              option.textContent =
                statusLabel(run.status || "running") + " · " +
                (run.question || runId) + " · " + runId;
              if (event.step === "run" && event.status === "running") {{
                selectedRun = runId;
                runSelect.value = runId;
              }}
              if (!selectedRun) {{
                selectedRun = runId;
                runSelect.value = runId;
              }}
            }}

            function addEvent(event) {{
              const runId = event.run_id;
              const runEvents = getRunEvents(runId);
              runEvents.set(event.event_id, event);
              updateRunOption(runId, event);
              if (runId === selectedRun) renderTimeline();
            }}

            function renderTimeline() {{
              timeline.replaceChildren();
              const runEvents = eventsByRun.get(selectedRun);
              if (!runEvents || runEvents.size === 0) {{
                timeline.textContent = "Đang chờ sự kiện cho lần chạy này...";
                summary.replaceChildren();
                return;
              }}

              const allEvents = Array.from(runEvents.values()).sort(
                (left, right) => left.event_id - right.event_id
              );
              const orderedEvents = allEvents;
              const eventsByAgent = new Map();
              for (const event of orderedEvents) {{
                const agent = agentKey(event);
                if (!eventsByAgent.has(agent)) eventsByAgent.set(agent, []);
                eventsByAgent.get(agent).push(event);
              }}
              const run = knownRuns.get(selectedRun) || {{}};
              const startEvent = allEvents.find(
                (event) => event.step === "run" && event.status === "running"
              ) || allEvents[0];
              const terminalEvent = [...allEvents].reverse().find(
                (event) =>
                  event.step === "run" &&
                  (event.status === "completed" || event.status === "failed")
              );
              const startTime = new Date(
                startEvent.time || run.started_at
              ).getTime();
              const endTime = terminalEvent
                ? new Date(terminalEvent.time).getTime()
                : Date.now();
              const elapsed = Number.isFinite(startTime)
                ? formatDuration(endTime - startTime)
                : "—";
              const metrics = [
                ["Trạng thái", terminalEvent
                  ? statusLabel(terminalEvent.status)
                  : statusLabel("running")],
                ["Bắt đầu", formatDate(startEvent.time || run.started_at)],
                ["Tổng thời gian chạy", elapsed],
                ["Tổng token LLM", (() => {{
                  const usage = tokenTotals(orderedEvents);
                  return usage
                    ? `${{formatTokens(usage.total_tokens)}} (vào ${{formatTokens(usage.input_tokens)}} · ra ${{formatTokens(usage.output_tokens)}})`
                    : "Chưa có dữ liệu usage";
                }})()],
              ];
              summary.replaceChildren();
              for (const [label, value] of metrics) {{
                const card = document.createElement("div");
                card.className = "metric";
                const metricLabel = document.createElement("div");
                metricLabel.className = "metric-label";
                metricLabel.textContent = label;
                const metricValue = document.createElement("div");
                metricValue.className = "metric-value";
                metricValue.textContent = value;
                card.append(metricLabel, metricValue);
                summary.appendChild(card);
              }}

              const agentContainers = new Map();
              for (const [agent, events] of eventsByAgent) {{
                const group = document.createElement("section");
                group.className = "agent-group";
                const agentHeader = document.createElement("div");
                agentHeader.className = "agent-header";
                const agentTitle = document.createElement("h2");
                agentTitle.textContent = agentLabels[agent] || agent;
                agentHeader.appendChild(agentTitle);
                const usage = tokenTotals(events);
                if (usage) {{
                  const tokenBadge = document.createElement("span");
                  tokenBadge.className = "agent-token";
                  tokenBadge.textContent =
                    `Tổng token: ${{formatTokens(usage.total_tokens)}} ` +
                    `(vào ${{formatTokens(usage.input_tokens)}} · ` +
                    `ra ${{formatTokens(usage.output_tokens)}})`;
                  agentHeader.appendChild(tokenBadge);
                }}
                group.appendChild(agentHeader);
                timeline.appendChild(group);
                agentContainers.set(agent, group);
              }}

              for (const event of orderedEvents) {{
                const card = document.createElement("section");
                card.className = "event " + event.status;
                const heading = document.createElement("div");
                heading.className = "event-heading";
                const title = document.createElement("h3");
                title.textContent = eventLabel(event.step);
                const badge = document.createElement("span");
                badge.className = "badge";
                badge.textContent = statusLabel(event.status);
                const time = document.createElement("span");
                time.className = "event-time";
                time.textContent = formatDate(event.time);
                heading.append(title, badge, time);
                card.appendChild(heading);

                const details = event.details || {{}};
                if (event.step === "run" && details.question) {{
                  const question = document.createElement("p");
                  question.textContent = "Câu hỏi: " + details.question;
                  card.appendChild(question);
                }}
                if (details.message) {{
                  const message = document.createElement("p");
                  if (event.status === "failed") message.className = "error";
                  message.textContent = details.message;
                  card.appendChild(message);
                }}
                if (event.step === "rag_search" && event.status === "completed") {{
                  const chunkSummary = document.createElement("p");
                  chunkSummary.textContent =
                    `Đã chọn ${{details.chunk_count || 0}} đoạn tài liệu liên quan.`;
                  card.appendChild(chunkSummary);

                  if (details.chunks?.length) {{
                    const chunks = document.createElement("ul");
                    chunks.className = "rag-chunks";
                    for (const chunk of details.chunks) {{
                      const item = document.createElement("li");
                      item.className = "rag-chunk";
                      item.textContent =
                        `${{chunk.document_name || "Không rõ tài liệu"}}` +
                        ` · ${{chunk.chapter || "Chưa xác định chương"}}` +
                        ` · ${{chunk.article_title || "Chưa xác định điều"}}`;
                      chunks.appendChild(item);
                    }}
                    card.appendChild(chunks);
                  }}
                }}
                if (
                  event.step === "route" &&
                  (details.selected_nodes || details.selected_node)
                ) {{
                  const selectedNodes = details.selected_nodes ||
                    [details.selected_node];
                  const branchLabels = {{
                    sql_processor: "SQL",
                    rag_processor: "RAG",
                  }};
                  const branch = document.createElement("p");
                  branch.textContent = "Đã chọn nhánh: " +
                    selectedNodes
                      .map((node) => branchLabels[node] || node)
                      .join(" + ");
                  card.appendChild(branch);
                }}
                if (details.candidate_tables) {{
                  const tables = document.createElement("p");
                  tables.textContent =
                    "Các bảng được chọn: " +
                    details.candidate_tables.join(", ");
                  card.appendChild(tables);
                }}
                if (details.join_paths) {{
                  const joins = document.createElement("p");
                  joins.textContent = "Đường JOIN: " + details.join_paths;
                  card.appendChild(joins);
                }}
                if (details.resolved_joins?.length) {{
                  const joins = document.createElement("ul");
                  for (const join of details.resolved_joins) {{
                    const item = document.createElement("li");
                    item.textContent =
                      `${{join.relationship || join.join_type}}: ` +
                      `${{join.left_table}}.${{join.left_column}} = ` +
                      `${{join.right_table}}.${{join.right_column}}`;
                    joins.appendChild(item);
                  }}
                  card.appendChild(joins);
                }}
                if (details.sql_query) {{
                  const sql = document.createElement("pre");
                  sql.textContent = "SQL được sinh:\\n" + details.sql_query;
                  card.appendChild(sql);
                }}
                if (event.step === "query_execution" &&
                    event.status === "completed") {{
                  const result = document.createElement("p");
                  result.textContent = details.has_data
                    ? "Kết quả: Có dữ liệu."
                    : "Kết quả: Không có dữ liệu.";
                  card.appendChild(result);
                }}
                if (event.step === "rag") {{
                  const message = document.createElement("p");
                  message.textContent = "Đã xử lý nhánh RAG.";
                  card.appendChild(message);
                }}
                agentContainers.get(agentKey(event)).appendChild(card);
              }}
              timeline.scrollTop = timeline.scrollHeight;
            }}

            async function loadRunsAndHistory() {{
              const response = await fetch(apiBase + "/runs");
              if (!response.ok) throw new Error("Không thể tải danh sách log.");
              const data = await response.json();
              const previousSelection = selectedRun;
              for (const run of data.runs || []) {{
                knownRuns.set(run.run_id, run);
                updateRunOption(run.run_id, {{
                  run_id: run.run_id,
                  time: run.started_at,
                  step: "run",
                  status: run.status,
                  details: {{ question: run.question }}
                }});
              }}
              if (previousSelection && knownRuns.has(previousSelection)) {{
                selectedRun = previousSelection;
                runSelect.value = previousSelection;
              }} else if (data.runs && data.runs.length) {{
                selectedRun = data.runs[0].run_id;
                runSelect.value = selectedRun;
              }} else {{
                runSelect.replaceChildren();
                const empty = document.createElement("option");
                empty.value = "";
                empty.textContent = "Chưa có lần chạy chatbot";
                runSelect.appendChild(empty);
                selectedRun = "";
              }}

              if (selectedRun) {{
                const historyResponse = await fetch(
                  apiBase + "/runs/" + encodeURIComponent(selectedRun)
                );
                if (historyResponse.ok) {{
                  const history = await historyResponse.json();
                  for (const event of history.events || []) addEvent(event);
                }}
              }}
              loadedRuns = true;
              renderTimeline();
            }}

            runSelect.addEventListener("change", async () => {{
              selectedRun = runSelect.value;
              if (selectedRun && !getRunEvents(selectedRun).size) {{
                try {{
                  const response = await fetch(
                    apiBase + "/runs/" + encodeURIComponent(selectedRun)
                  );
                  if (response.ok) {{
                    const history = await response.json();
                    for (const event of history.events || []) addEvent(event);
                  }}
                }} catch (error) {{
                  connection.textContent = error.message;
                }}
              }}
              renderTimeline();
            }});

            const eventSource = new EventSource(apiBase + "/events");
            eventSource.onopen = () => {{
              connection.textContent = "Đang nhận sự kiện trực tiếp";
              if (!loadedRuns) {{
                loadRunsAndHistory().catch((error) => {{
                  connection.textContent = error.message;
                  connection.className = "error";
                }});
              }}
            }};
            eventSource.onmessage = (message) => {{
              try {{
                addEvent(JSON.parse(message.data));
              }} catch (error) {{
                connection.textContent = "Không đọc được event: " + error.message;
                connection.className = "error";
              }}
            }};
            eventSource.onerror = () => {{
              connection.textContent = "Mất kết nối; trình duyệt đang tự kết nối lại...";
              connection.className = "error";
            }};
            window.setInterval(() => {{
              const runEvents = eventsByRun.get(selectedRun);
              const finished = runEvents && Array.from(runEvents.values()).some(
                (event) =>
                  event.step === "run" &&
                  (event.status === "completed" || event.status === "failed")
              );
              if (runEvents && runEvents.size && !finished) renderTimeline();
            }}, 1000);
          </script>
        </body>
      </html>
      """,
      height=820,
      scrolling=False,
  )
