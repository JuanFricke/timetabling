# Arquitetura — Timetabling Híbrido CP + Local Search

## Índice

1. [Visão Geral](#visão-geral)
2. [Stack Tecnológica](#stack-tecnológica)
3. [Modelo de Domínio](#modelo-de-domínio)
4. [Modelo de Slots por Turma](#modelo-de-slots-por-turma)
5. [Algoritmo Híbrido](#algoritmo-híbrido)
6. [Estrutura de Arquivos](#estrutura-de-arquivos)
7. [Schema JSON](#schema-json)
8. [Schema do Banco de Dados](#schema-do-banco-de-dados)
9. [Formato de Saída](#formato-de-saída)
10. [Fluxo de Execução](#fluxo-de-execução)

---

## Visão Geral

O sistema resolve o **Problema de Grade Horária Escolar** (*School Timetabling Problem*), que pertence à classe NP-difícil de problemas de otimização combinatória.

O objetivo é atribuir tuplas `(turma, matéria, professor, dia, slot)` satisfazendo:

- **Hard constraints** (restrições rígidas): nunca podem ser violadas.
- **Soft constraints** (restrições flexíveis): devem ser minimizadas de acordo com seus pesos.

A abordagem híbrida combina:
1. **CP-SAT** (Constraint Programming): garante viabilidade com todas as hard constraints satisfeitas.
2. **Local Search** (Hill Climbing): melhora a qualidade da solução minimizando o custo ponderado das soft constraints.

---

## Stack Tecnológica

| Componente | Tecnologia | Papel |
|------------|-----------|-------|
| Linguagem | Python 3.13 | Toda a lógica do sistema |
| Gerenciador de pacotes | uv | Gerenciamento de dependências e execução |
| Solver CP | OR-Tools CP-SAT (Google) | Fase 1: busca de solução viável |
| ORM | SQLAlchemy 2.0 | Mapeamento objeto-relacional |
| Banco de dados | MySQL 8 | Persistência de runs e resultados |
| Validação | Pydantic v2 | Parsing e validação dos JSONs de entrada |
| Containerização | Docker + Compose | Empacotamento e orquestração |
| CLI | Rich | Output formatado no terminal |

---

## Modelo de Domínio

```
School
  ├── days: list[str]         (ex: ["Segunda", ..., "Sexta"])
  └── slots: list[SlotDef]   (ex: [{id:1, label:"07:00"}, ...])

Teacher
  ├── id: str
  ├── name: str
  └── subjects: list[str]    (IDs das matérias que pode lecionar)

Subject
  ├── id: str
  └── name: str

Class (Turma)
  ├── id: str
  ├── name: str
  ├── level: str              (ex: "fundamental", "medio")
  └── available_slots: list[int]  (IDs dos slots que a turma frequenta)

Requirement (Requisito semanal)
  ├── class_id: str
  ├── subject_id: str
  ├── teacher_id: str
  └── hours_per_week: int

HardBlock (restrição rígida)
  ├── TeacherUnavailableBlock  (professor indisponível em day+slot)
  └── ClassUnavailableBlock    (turma indisponível em day+slot)

SoftBlock (restrição flexível com peso)
  ├── TeacherPreferredSlotBlock
  ├── ClassPreferredSlotBlock
  ├── AvoidLastSlotBlock
  ├── AvoidTeacherGapsBlock
  ├── SubjectSpreadBlock
  └── MaxConsecutiveBlock

ScheduleEntry (unidade da solução)
  ├── class_id, subject_id, teacher_id
  ├── day: str
  └── slot: int

Schedule (solução completa)
  ├── entries: list[ScheduleEntry]
  └── soft_score: int   (penalidade total — menor = melhor)
```

---

## Modelo de Slots por Turma

Diferente de um modelo global com `slots_per_day` fixo, cada turma declara
explicitamente quais slots ela utiliza. Isso permite que turmas com turnos
diferentes coexistam no mesmo problema:

```
Slot  Horário    Fundamental (manhã)    Médio (manhã + tarde)
  1   07:00           ✓                        ✓
  2   08:00           ✓                        ✓
  3   09:00           ✓                        ✓
  4   10:00           ✓                        ✓
  5   13:00           —                        ✓
  6   14:00           —                        ✓
  7   15:00           —                        ✓
  8   16:00           —                        ✓
```

**Consequência importante para conflitos de professor:**
Um professor pode ser atribuído ao slot 5 (13:00) de uma turma de médio e ao
slot 2 (08:00) de uma turma fundamental no mesmo dia, sem conflito — porque
esses slots nunca se sobrepõem.

O solver cria variáveis de decisão **apenas** para `slot ∈ class.available_slots`,
reduzindo o espaço de busca e evitando checagens desnecessárias.

---

## Algoritmo Híbrido

### Fase 1 — CP-SAT (OR-Tools)

**Arquivo:** `src/timetabling/solver/cp_solver.py`

**Variáveis de decisão:**
```
x[class_id, subject_id, teacher_id, day, slot] ∈ {0, 1}
```
Criadas apenas para slots em `class.available_slots` e não bloqueados por hard blocks.

**Hard constraints codificadas:**

| # | Constraint | Formulação |
|---|-----------|------------|
| 1 | Cumprir horas semanais | `sum(x[c,s,t,d,*]) == hours_per_week` para cada requirement |
| 2 | Uma aula por (turma, dia, slot) | `sum(x[c,*,*,d,sl]) <= 1` |
| 3 | Um professor por (dia, slot) | `sum(x[*,*,t,d,sl]) <= 1` |
| 4 | Slots disponíveis da turma | variáveis só existem para `sl ∈ class.available_slots` |
| 5 | Professor bloqueado | variável não criada para `(t,d,sl) ∈ blocked_teacher` |
| 6 | Turma bloqueada | variável não criada para `(c,d,sl) ∈ blocked_class` |

**Resultado:** primeira solução viável encontrada dentro do time limit.

### Fase 2 — Local Search (Hill Climbing)

**Arquivo:** `src/timetabling/solver/local_search.py`

**Movimentos de vizinhança:**

- **SWAP**: troca o `(day, slot)` de dois entries da mesma turma.
- **MOVE**: move um entry para um `(day, slot)` diferente, dentro dos slots disponíveis da turma.

**Critério de aceitação:** aceita o movimento se `novo_score < score_atual` (Hill Climbing).

**Verificação de viabilidade após cada movimento:**
1. Sem colisão de turma em `(day, slot)`.
2. Sem colisão de professor em `(day, slot)`.
3. Slot dentro de `class.available_slots`.
4. Não viola nenhum hard block.

**Critério de parada:** `max_iterations` atingido ou `soft_score == 0`.

### Avaliador de Soft Constraints

**Arquivo:** `src/timetabling/solver/evaluator.py`

Calcula a penalidade total (soma ponderada das violações):

| Tipo | Cálculo da penalidade |
|------|-----------------------|
| `teacher_preferred_slot` | `+weight` se professor NÃO está no slot preferido |
| `class_preferred_slot` | `+weight` se turma NÃO tem aula no slot preferido |
| `avoid_last_slot` | `+weight` por dia em que a turma tem aula no último slot |
| `avoid_teacher_gaps` | `+weight × nº_buracos` por dia com lacunas no horário do professor |
| `subject_spread` | `+weight × (ocorrências_no_dia - 1)` para cada dia com >1 aula da matéria |
| `max_consecutive` | `+weight` por vez que o limite de aulas consecutivas é excedido |

---

## Estrutura de Arquivos

```
timetabling/
├── Dockerfile                          ← Imagem Python + uv
├── docker-compose.yml                  ← Orquestração app + MySQL
├── pyproject.toml                      ← Dependências e metadados uv
├── .python-version                     ← Python 3.13
├── .env.example                        ← Template de configuração
├── .gitignore
│
├── migrations/
│   └── init.sql                        ← DDL do banco MySQL
│
├── docs/
│   └── ARCHITECTURE.md                 ← Este arquivo
│
├── data/
│   ├── input/
│   │   ├── hard_blocks.json            ← Entrada principal (problema + hard constraints)
│   │   └── soft_blocks.json            ← Soft constraints com pesos
│   └── output/
│       └── <NomeTurma>.csv             ← Gerado pelo solver
│
└── src/timetabling/
    ├── __init__.py
    ├── main.py                         ← CLI: python -m timetabling.main solve
    ├── config.py                       ← Leitura de variáveis de ambiente
    │
    ├── models/
    │   ├── __init__.py
    │   └── domain.py                   ← Pydantic: todos os modelos do domínio
    │
    ├── db/
    │   ├── __init__.py
    │   ├── schema.py                   ← SQLAlchemy ORM (tabelas)
    │   └── repository.py               ← CRUD: upsert_problem, save_schedule, load_latest
    │
    ├── io/
    │   ├── __init__.py
    │   ├── json_loader.py              ← load_hard_blocks(), load_soft_blocks()
    │   └── csv_exporter.py             ← export(schedule, problem, output_dir)
    │
    └── solver/
        ├── __init__.py
        ├── cp_solver.py                ← solve(problem) → Schedule | None
        ├── evaluator.py                ← score(schedule, soft, problem) → int
        └── local_search.py             ← improve(initial, soft, problem) → (Schedule, int)
```

---

## Schema JSON

### hard_blocks.json — Schema completo

```json
{
  "school": {
    "days": ["string"],
    "slots": [{"id": "int (1+)", "label": "string (ex: '07:00')"}]
  },
  "teachers": [
    {
      "id": "string",
      "name": "string",
      "subjects": ["subject_id"]
    }
  ],
  "classes": [
    {
      "id": "string",
      "name": "string",
      "level": "string (opcional, ex: 'fundamental')",
      "available_slots": ["slot_id"]
    }
  ],
  "subjects": [
    {"id": "string", "name": "string"}
  ],
  "requirements": [
    {
      "class_id": "string",
      "subject_id": "string",
      "teacher_id": "string",
      "hours_per_week": "int (> 0)"
    }
  ],
  "hard_blocks": [
    {"type": "teacher_unavailable", "teacher_id": "string", "day": "string", "slot": "int"},
    {"type": "class_unavailable",   "class_id":   "string", "day": "string", "slot": "int"}
  ]
}
```

### soft_blocks.json — Schema completo

```json
{
  "soft_blocks": [
    {"type": "teacher_preferred_slot", "teacher_id": "string", "day": "string", "slot": "int", "weight": "int (> 0)"},
    {"type": "class_preferred_slot",   "class_id":   "string", "day": "string", "slot": "int", "weight": "int (> 0)"},
    {"type": "avoid_last_slot",        "class_id":   "string", "weight": "int (> 0)"},
    {"type": "avoid_teacher_gaps",     "teacher_id": "string", "weight": "int (> 0)"},
    {"type": "subject_spread",         "class_id":   "string", "subject_id": "string", "weight": "int (> 0)"},
    {"type": "max_consecutive",        "class_id":   "string", "max_consecutive": "int (> 0)", "weight": "int (> 0)"}
  ]
}
```

---

## Schema do Banco de Dados

```
slots            (id PK, label)
teachers         (id PK, name)
subjects         (id PK, name)
teacher_subjects (teacher_id FK, subject_id FK) PK composta
classes          (id PK, name, level)
class_available_slots (class_id FK, slot_id FK) PK composta
requirements     (id PK AI, class_id FK, subject_id FK, teacher_id FK, hours_per_week)

schedule_runs    (id PK AI, created_at, cp_feasible, soft_score_initial,
                  soft_score_final, ls_iterations, notes)
schedule_entries (id PK AI, run_id FK, class_id FK, subject_id FK,
                  teacher_id FK, day, slot_id FK)
                  UNIQUE(run_id, class_id, day, slot_id)
                  UNIQUE(run_id, teacher_id, day, slot_id)
```

Cada execução do solver cria um `schedule_run` com todos os `schedule_entries`
associados, permitindo histórico e comparação entre runs.

---

## Formato de Saída

Um arquivo CSV por turma em `data/output/`:

```
Slot,Label,Segunda,Terca,Quarta,Quinta,Sexta
1,07:00,Matematica - Ana Paula,,Portugues - Carlos Mendes,,
2,08:00,,Historia - Rodrigo Lima,,,Matematica - Ana Paula
3,09:00,Biologia - Beatriz Costa,Matematica - Ana Paula,,,
4,10:00,,Portugues - Carlos Mendes,,Biologia - Beatriz Costa,
```

Turma fundamental (`available_slots: [1,2,3,4]`): 4 linhas de slot.  
Turma médio (`available_slots: [1,2,3,4,5,6,7,8]`): 8 linhas de slot.

Células vazias indicam que não há aula naquele (dia, slot) para a turma.

---

## Fluxo de Execução

```
main.py solve
    │
    ├─► json_loader.load_hard_blocks()    → HardBlocksInput (validado Pydantic)
    ├─► json_loader.load_soft_blocks()    → SoftBlocksInput (validado Pydantic)
    │
    ├─► cp_solver.solve(problem)
    │       │  Cria variáveis CP-SAT para cada (class, req, day, slot válido)
    │       │  Codifica hard constraints como restrições lineares
    │       │  Executa solver com time limit
    │       └─► Schedule (viável) | None (inviável → exit)
    │
    ├─► evaluator.score(initial, soft, problem)   → soft_score inicial
    │
    ├─► local_search.improve(initial, soft, problem, max_iterations)
    │       │  Loop: gera move aleatório (swap | move)
    │       │  Verifica viabilidade (hard constraints)
    │       │  Avalia novo score
    │       │  Aceita se score melhorou (Hill Climbing)
    │       └─► (Schedule melhorado, nº iterações)
    │
    ├─► repository.save_schedule()        → persiste no MySQL (opcional)
    │
    └─► csv_exporter.export()             → gera um CSV por turma
```
