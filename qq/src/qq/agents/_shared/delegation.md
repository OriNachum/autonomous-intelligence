## Task Delegation Strategy

For large-scale tasks, use hierarchical delegation to process efficiently.

### Capacity Limits

| Limit | Value | Description |
|-------|-------|-------------|
| Queue size | 10 | Tasks per agent queue |
| Depth | 3 | Levels of sub-agents |
| Max items | 1,000 | 10 × 10 × 10 hierarchical |

### Splitting Strategy

When given N items to process:

| Items | Strategy |
|-------|----------|
| 1 | Process directly |
| 2-10 | Use `delegate_task` or `run_parallel_tasks` |
| 11-100 | Split into ~10 batches, delegate each |
| 101-1000 | Split into 10 → each splits into 10 → leaf processes ~10 |

### Example: Processing 100 Files

```
Root Agent (depth 0):
├── schedule_tasks() with 10 batch tasks
│   ├── Batch 1: "Process files 1-10"
│   ├── Batch 2: "Process files 11-20"
│   └── ... (8 more batches)
└── execute_scheduled_tasks()

Each Child (depth 1):
├── Receives ~10 files
├── run_parallel_tasks() for each file
└── Returns aggregated results
```

### When to Delegate

**DO delegate when:**
- Task involves 2+ files or multiple distinct concerns
- Work can be parallelized (items are independent)
- Processing is uniform across items

**DON'T delegate when:**
- Task is a single-file or simple operation
- Items have dependencies
- At max depth (use `get_queue_status()` to check `can_spawn`)

### Tools

**Immediate execution:**
```
run_parallel_tasks('[{"task": "..."}, {"task": "..."}]')
```

**Scheduled batch execution:**
```
schedule_tasks('[{"task": "...", "priority": 10}]')
execute_scheduled_tasks()
```

**Check status before delegating:**
```
get_queue_status()  # Returns can_spawn, current_depth
```

### Results Aggregation

After delegation:
1. Collect all sub-agent results
2. Aggregate/summarize findings
3. Present unified response to user
