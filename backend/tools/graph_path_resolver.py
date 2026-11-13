import json
import itertools
import networkx as nx


class GraphPathResolver:

  def __init__(self, json_config_path: str = "table_relationships_and_paths.json"):
    """Khởi tạo đồ thị kết nối cơ sở dữ liệu từ file JSON.
    Sử dụng MultiDiGraph để lưu trữ đồng thời nhiều cạnh song song (ví dụ: Người thực hiện và Người quản lý).
    """
    with open(json_config_path, "r", encoding="utf-8") as f:
      self.data = json.load(f)

    self.graph = nx.MultiDiGraph()
    self._build_graph()
    self.path_graph = self.graph.to_undirected()

  def _build_graph(self):
    # Thêm toàn bộ các nodes vào đồ thị
    for node in self.data["nodes"]:
      self.graph.add_node(
          node["id"],
          display_name=node["display_name"],
          table_name=node["table_name"],
          description=node["description"],
      )

    # Thêm toàn bộ các edges (MultiDiGraph cho phép nhiều cạnh nối giữa 2 node)
    for edge in self.data["edges"]:
      self.graph.add_edge(
          edge["source"],
          edge["target"],
          label=edge["label"],
          from_column=edge["join_condition"]["from_column"],
          to_column=edge["join_condition"]["to_column"],
          relationship_type=edge["relationship_type"],
      )

  def resolve_join_paths(self, candidate_tables: list) -> dict:
    """Nhận danh sách bảng candidate từ bước Vector Retrieval và tìm đường đi

    bằng cách xét TOÀN BỘ CÁC TỔ HỢP CẶP BẢNG (Combinations). Các bảng
    trung gian trên đường đi cũng được thêm vào candidate_tables nếu còn thiếu.
    """
    if not candidate_tables:
      return {"status": "error", "message": "Danh sách bảng trống."}

    candidate_tables = list(dict.fromkeys(candidate_tables))

    # Nếu chỉ có 1 bảng, không cần JOIN
    if len(candidate_tables) == 1:
      return {
          "candidate_tables": candidate_tables,
          "path_tables": [],
          "resolved_joins": [],
          "graph_traversal_steps": f"Chỉ có 1 bảng [{candidate_tables[0]}], không cần JOIN.",
      }

    resolved_joins = []
    explanations = []
    expanded_tables = list(candidate_tables)

    # SỬ DỤNG COMBINATIONS: Xét mọi cặp bảng có thể có trong danh sách candidate, 
    # bất kể thứ tự đứng trước hay sau (ví dụ: task và employee sẽ luôn được xét trực tiếp với nhau).
    for source_table, target_table in itertools.combinations(candidate_tables, 2):
      if source_table == target_table:
        continue

      # JOIN có thể được duyệt theo cả hai chiều, dù cạnh khai báo có hướng.
      try:
        path = nx.shortest_path(
            self.path_graph, source=source_table, target=target_table
        )
        for table_name in path:
          if table_name not in expanded_tables:
            expanded_tables.append(table_name)
        self._extract_edges_from_path(path, resolved_joins, explanations)
      except nx.NetworkXNoPath:
        explanations.append(
            f"Không tìm thấy đường nối giữa {source_table} và {target_table}"
        )

    if not resolved_joins:
      explanations.append("Không tìm thấy đường nối hợp lệ nào giữa các bảng candidate.")

    return {
        "candidate_tables": expanded_tables,
        "path_tables": [
            table_name
            for table_name in expanded_tables
            if table_name not in candidate_tables
        ],
        "resolved_joins": resolved_joins,
        "graph_traversal_steps": " | ".join(explanations),
    }

  def _extract_edges_from_path(self, path: list, resolved_joins: list, explanations: list):
    """Hàm phụ trợ trích xuất thông tin chi tiết các cạnh JOIN từ một path tìm được."""
    for i in range(len(path) - 1):
      u = path[i]
      v = path[i + 1]
      
      # Lấy các cạnh ở cả hai hướng; quan hệ JOIN có thể được khai báo
      # ngược với thứ tự các bảng trên đường đi.
      edge_options = []
      for source, target, reversed_columns in (
          (u, v, False),
          (v, u, True),
      ):
        edge_dict = self.graph.get_edge_data(source, target)
        if edge_dict:
          edge_options.extend(
              (edge_data, reversed_columns)
              for edge_data in edge_dict.values()
          )

      for edge_data, reversed_columns in edge_options:
        left_column = (
            edge_data["to_column"]
            if reversed_columns
            else edge_data["from_column"]
        )
        right_column = (
            edge_data["from_column"]
            if reversed_columns
            else edge_data["to_column"]
        )
        join_info = {
            "left_table": u,
            "right_table": v,
            "left_column": left_column,
            "right_column": right_column,
            "join_type": "INNER JOIN",
            "relationship": edge_data["label"],
            "description": (
                f"Kết nối [{self.graph.nodes[u]['display_name']}] với"
                f" [{self.graph.nodes[v]['display_name']}] qua"
                f" {u}.{left_column} = {v}.{right_column}"
            ),
        }

        # Tránh thêm trùng lặp các cặp join đã có
        if join_info not in resolved_joins:
          resolved_joins.append(join_info)

        readable_step = (
            f"[{self.graph.nodes[u]['display_name']}] --("
            f"{edge_data['label']})-- "
            f"[{self.graph.nodes[v]['display_name']}]"
        )
        if readable_step not in explanations:
          explanations.append(readable_step)