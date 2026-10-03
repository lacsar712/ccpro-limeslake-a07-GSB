# LimeSlake-01 · 石灰熟化池作业板

厂区熟化池平面图作业基线（Flask + Jinja + Stimulus）。主界面是按厂区排布的池位瓦片，点选后在右侧抽屉登记峰值温度并改状态——不是侧栏双列表 CRUD。

## 技术栈

| 层 | 技术 |
| --- | --- |
| Web | Flask 3 · Blueprints · Flask-Login · Jinja2 · Stimulus CDN |
| 数据 | SQLAlchemy · PostgreSQL 15 |
| 部署 | Docker Compose · Gunicorn |

## 路径与端口

- **项目路径**：`d:\work\document\bytecode\claudeCodePro\LimeSlake\LimeSlake-01`
- **Web**：http://localhost:4730
- **PostgreSQL**：localhost:6130

## 演示账号

| 用户名 | 密码 | 角色 |
| --- | --- | --- |
| `admin` | `123456` | 管理员 |
| `worker` | `123456` | 操作工 |

登录页已预填 `admin` / `123456`。启动时 entrypoint 会建表并写入种子数据（示范厂区：**东湾石灰厂**）。

## 主界面

- **熟化池平面图**（`/board/`）：CSS 网格池位瓦片，按状态着色（注水中 / 熟化中 / 已出灰）
- 顶部厂区切换芯片（多厂时切换）
- 点击瓦片 → 右侧抽屉展示最近 `SlakeBatch`，可登记峰值温度并变更池状态
- 主导航不再挂「熟化池列表 / 批次列表」；旧 `/ponds/`、`/batches/` 路由仍保留但不作为作业入口

## 业务规则

1. 熟化池状态不可设为「已出灰」（`drawn`），除非该池**最近一条** `SlakeBatch` 的 `peakTempC` 已记录且 **≥ 60℃**。
2. **邻池放行签**：同厂若已有别的池处于「熟化中」（热邻池），某池要从「注水中」进入「熟化中」前，必须先持有一张**未核销**的邻池放行签。
   - 签字段：目标池、热邻池、签发时刻、签发人、核销时刻（可空）。
   - 热邻池须与目标池**同厂**且签发当时为「熟化中」；同一目标池的未核销签**最多一张**（数据库部分唯一索引兜底，两名管理员并发开签也只落一张）。
   - **仅管理员**可签发与核销。
   - 登记批次 / 纯改池态让注水池进入熟化中时：系统在**同一事务**内先把核销时刻写入放行签，批次才入库、池态才转「熟化中」；无签而有热邻则整笔回滚并拦下。同厂无热邻时无须持签。
   - 顶栏挂「放行签」（带未核销计数徽标），专页 `/passes/` 含未核销列表、签发、核销；平面图上对「注水中 + 有热邻 + 无签」的池标记**待放行**。

规则实现：`app/services/rules.py`；放行签模型：`app/models.py::ReleasePass`；路由：`app/blueprints/passes.py`。

种子数据：东湾石灰厂两口同厂池——`P-01` 已熟化中（热邻），`P-02` 注水中且未持签（平面图上显示待放行）。

## 快速启动

```bash
cd d:\work\document\bytecode\claudeCodePro\LimeSlake\LimeSlake-01
docker compose up --build
```

浏览器打开 http://localhost:4730

停止：

```bash
docker compose down
```

## 目录结构

```
LimeSlake-01/
├── docker-compose.yml
├── Dockerfile
├── entrypoint.sh
├── wsgi.py
├── app/
│   ├── __init__.py          # 工厂 + seed
│   ├── models.py
│   ├── services/rules.py
│   └── blueprints/{auth,board,ponds,batches}
├── templates/
│   └── board/floor.html     # 平面图 + 抽屉
└── static/
```
