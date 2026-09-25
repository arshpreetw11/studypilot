import { addDays, fmtShort, todayISO } from './dates'

// A realistic 3rd-semester B.Tech syllabus, with exam dates relative to today
export function sampleSyllabus() {
  const t = todayISO()
  const d = (n) => `${fmtShort(addDays(t, n))} ${addDays(t, n).slice(0, 4)}`
  return `Data Structures & Algorithms — Exam: ${d(14)}
- Arrays & Hashing
- Linked Lists, Stacks & Queues
- Trees & Heaps
- Graph Algorithms (BFS, DFS, Dijkstra)
- Dynamic Programming

Database Management Systems — Exam: ${d(18)}
Unit 1: ER Model, Relational Algebra
Unit 2: Normalization (1NF to BCNF), SQL Joins & Subqueries
Unit 3: Transactions & Concurrency Control

Operating Systems — Exam: ${d(22)}
Unit 1: Processes & Threads, CPU Scheduling
Unit 2: Deadlocks, Memory Management
Unit 3: Virtual Memory & Paging, File Systems`
}
