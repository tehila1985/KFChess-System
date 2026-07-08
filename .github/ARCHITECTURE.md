# 🏗️ ארכיטקטורת King-Fu-Chess

## 📌 תיאור כללי

**King-Fu-Chess** הוא משחק שחמט בזמן אמת שבו שני שחקנים זזים במקביל ללא תורות. כל כלי נע בפיזיקה אמיתית עם זמן תנועה, וניצחון קיים רק בלכידת המלך.

---

## 🏛️ מבנה הפרויקט

```
chess/
├── main.py                    # Entry point - טוען את runner
├── engine/
│   ├── __init__.py
│   ├── board.py              # ניהול לוח (grid operations)
│   ├── pieces.py             # כללי תנועה, סוגי כלים, registry
│   ├── game_logic.py         # ⚡ מנוע המשחק (התנגשויות, תנועות)
│   ├── validator.py          # validation של לוח בתחילה
│   └── runner.py             # parsing קלט וקריאה ל-engine
├── utils/
│   └── parser.py             # parse input format
├── tests/                    # בדיקות יחידה
└── .github/
    ├── kong_fu_chess_requirements.md
    ├── ARCHITECTURE.md       # קובץ זה
    └── GAME_LOGIC_FUNCTIONS.md
```

---

## 🔧 קומות הארכיטקטורה

### 1️⃣ **Board Layer** (`engine/board.py`)
**אחראי:** ניהול הלוח הפיזי

| פונקציה | מטרה |
|---------|------|
| `in_bounds()` | בדיקה אם משבצת בתוך גבולות הלוח |
| `get()`, `set()` | קריאה וכתיבה לתא |
| `is_empty()` | בדיקה אם תא ריק |
| `is_path_blocked()` | בדיקה אם כלים חוסמים נתיב (למעט Jumpers) |
| `move_piece()` | תנועה של כלי (עם חזרה מה שנלכד) |
| `display()` | הדפסה של הלוח |

**חוקים:**
- Knight דוקפץ (לא נחסם)
- כלים אחרים חסומים על ידי כלים בנתיב

---

### 2️⃣ **Pieces Layer** (`engine/pieces.py`)
**אחראי:** הגדרת סוגי כלים וכללי התנועה שלהם

#### **Strategy Pattern - MovementRule**
כל סוג כלי יש rule נפרד:

```python
MovementRule (abstract)
├── KingRule        # 1 משבצת בכל כיוון
├── RookRule        # קו ישר
├── BishopRule      # אלכסון
├── QueenRule       # Rook + Bishop
├── KnightRule      # L-shape (עם is_jumper=True)
└── PawnRule        # קדימה/לכידה אלכסונית
```

#### **Registry Pattern - PieceRegistry**
מרשם מרכזי של כל הכלים ועל הקונפיגורציה:

```python
PieceRegistry
├── _registry       # מילון {code: PieceType}
├── MOVE_DURATION_MS # זמנים (K:1000, N:3000, P:500, etc.)
├── PIECE_SCORE     # ערכים (P:1, N:3, Q:9, K:∞)
├── JUMP_DURATION_MS # זמן קפיצה (1000ms)
├── register()      # הוסף כלי חדש
└── get()           # קבל כלי לפי קוד
```

**יתרון:** קל להוסיף כלי חדש (Drone) ללא שינוי בקוד הקיים.

---

### 3️⃣ **Game Logic Layer** (`engine/game_logic.py`) ⚡
**אחראי:** סימולציה, תנועות, התנגשויות, ניקוד

#### **Classes**

**Action** - מייצגת פעולה יחידה:
- `start`, `end` - משבצות
- `start_time`, `duration` - תזמון
- `end_time` - מחושב (start_time + duration)
- `is_jump` - האם זו קפיצה (start == end)

**GameEngine** - מנוע המשחק:
- `action_queue[]` - תור של פעולות פעילות
- `current_time` - זמן הסימולציה
- `selected` - הכלי שנבחר להזזה
- `scores{'w':, 'b':}` - ניקוד

#### **Flow לוגי**

```
runner: click(x, y) / jump(x, y) / wait(ms)
                ↓
        GameEngine methods
                ↓
        _flush_actions() ← הליבה!
                ↓
    1. התנגשויות head-to-head
    2. קפיצות תופסות מגיעים
    3. תנועות רגילות
    4. קידום חיילים
                ↓
        עדכון לוח וניקוד
```

**זהו ה-"גלב" של המנוע** - כאן מתרחש כל המשחק!

---

### 4️⃣ **Input/Output Layer**

#### **Parser** (`utils/parser.py`)
```
קלט format:
Board:
wR . bR
. . .

Commands:
click 50 50
wait 1000
click 150 50
```

#### **Runner** (`engine/runner.py`)
```python
1. Parse input
2. Validate board
3. Create Board & GameEngine
4. Execute commands in order
5. Output state as needed
```

---

## ⚙️ **Config Centralization**

כל ה-Configuration מרוכז ב-**PieceRegistry**:

```python
# pieces.py
MOVE_DURATION_MS = {
    'K': 1000,   # מלך איטי (חשוב להגנה)
    'Q': 2000,   # מלכה איטית
    'R': 2000,   # צריח איטי
    'B': 2000,   # רץ איטי
    'N': 3000,   # פרש איטי ביותר (כי קופץ)
    'P': 500,    # חייל מהיר
}

PIECE_SCORE = {
    'K': ∞,      # מלך = משחק מוגמר
    'Q': 9,
    'R': 5,
    'B': 3,
    'N': 3,
    'P': 1,
}

JUMP_DURATION_MS = 1000  # קפיצה קצרה יותר מתנועה
```

**יתרון:** עדכון ערכים פשוט וקל לעתיד (כקובץ config או database).

---

## 🔄 **Data Flow - דוגמה**

```
1. runner: click(50, 50) → בחירת wN
   └─ GameEngine.selected = (0, 0)

2. runner: click(150, 250) → הזזה
   └─ GameEngine.click() בודק:
      ├─ _piece_type() → Knight
      ├─ is_legal_move() → חוקי
      ├─ is_path_blocked() → False (Knight קופץ)
      ├─ _is_moving() → False
      ├─ _is_destination_taken() → False
      └─ יצור Action(start=(0,0), end=(2,1), start_time=0, duration=3000)

3. runner: wait(2000)
   └─ current_time = 2000
   └─ _flush_actions() → בודקות את כל Actions עם end_time <= 2000
   └─ לא בזמן עדיין (end_time = 3000)

4. runner: wait(1000)
   └─ current_time = 3000
   └─ _flush_actions() → end_time = 3000 <= 3000 ✓
   └─ בצע את התנועה → board.move_piece((0,0), (2,1))
   └─ הכלי הגיע!
```

---

## 🎯 **Scalability Design**

### **עכשיו (CLI)**
- Single GameEngine per game
- In-memory board

### **העתיד (Server)**
- Multiple GameEngines (one per game)
- PieceRegistry centralized (config server)
- Networking layer (distribute actions)
- Database for persistence

**הנקודה:** ה-engine כעת **עצמאי מהרשת** - קל להכניס אותו לשרת.

---

## 🧪 **Testing Strategy**

כל שכבה בדוקה:
- **board.py** - בדיקות חסימה, תנועה
- **pieces.py** - כללי כל סוג כלי
- **game_logic.py** - תנועות, התנגשויות, קופיצות
- **validator.py** - validation לוח
- **parser.py** - parsing input

---

## 📊 **Key Design Patterns**

| Pattern | מקום | מטרה |
|---------|------|------|
| **Strategy** | pieces.py | MovementRule - כללים גמישים |
| **Registry** | pieces.py | PieceRegistry - קונפיגורציה מרכזית |
| **State Machine** | game_logic.py | Action queue עם state transitions |
| **Snapshot** | game_logic.py | board grid snapshot לפתרון התנגשויות |

---

## 🚀 **Performance Notes**

- **Action Queue:** O(n) flush כאשר n = מספר פעולות בזמן נתון
- **Path Blocking:** O(d) כאשר d = מרחק בנתיב
- **Collision Detection:** O(n²) worst case (קטן מאד בפועל)

**למיליוני players:** צריך שרת כך שכל game בנפרד, ו-matchmaking להתאמה.

---

## 📝 **Code Quality Goals**

✅ **Clean Code** - שכבות ברורות, אחריויות חלוקות  
✅ **Extensible** - קל להוסיף כלים, אנימציות, כללים  
✅ **Testable** - כל פונקציה בדוקה  
✅ **Configurable** - קונפיגורציה מרכזית  
✅ **Scalable** - עצמאות מfrontend/network  

---

**Version:** 1.0  
**Last Updated:** 2026-07-09  
**Owner:** Team
