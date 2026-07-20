# 🔧 פונקציות GameEngine - תיעוד מפורט

## 📋 סקירה כללית

קובץ `server/game_logic.py` מכיל את **לב המנוע** של King-Fu-Chess.
כאן קורות כל התנועות, ההתנגשויות, והפתרונות של הסכסוכים בין כלים.

---

## 🎯 Pub | Classes

### **Action Class**

**מטרה:** מייצגת פעולה יחידה - תנועה או קפיצה של כלי בלוח.

```python
class Action:
    start: (row, col)           # משבצת התחלה
    end: (row, col)             # משבצת סיום
    start_time: int (ms)        # בה-זמן הפעולה נקבעה
    duration: int (ms)          # כמה זמן הפעולה ממשכת
    
    @property
    end_time: int               # start_time + duration
    
    @property
    is_jump: bool               # האם זו קפיצה? (start == end)
```

**דוגמאות:**
- **תנועה רגילה:** `Action((0,0), (2,1), start_time=0, duration=3000)` → Knight נע
- **קפיצה:** `Action((1,1), (1,1), start_time=500, duration=1000)` → אותו תא, "אויר"

---

### **GameEngine Class**

**מטרה:** מנוע המשחק - מנהל את כל ההגיון של המשחק.

#### **State Variables**

```python
self.board              # Board object - תמונת מצב הלוח
self.selected           # (row, col) של הכלי שנבחר, או None
self.current_time       # זמן סימולציה נוכחי (ms)
self.action_queue[]     # רשימת כל הפעולות הפעילות
self.scores{'w', 'b'}   # ניקוד לכל שחקן
```

---

## 🔍 Pub | Helper Methods (Private)

### **1. `_piece_type(r, c)`**

```python
def _piece_type(self, r, c) -> PieceType | None:
    """קבל את סוג הכלי במיקום (r, c). מחזיר PieceType או None אם ריק."""
```

**מטרה:** זיהוי איזה סוג כלי נמצא במשבצת.

**חוזר:** 
- `PieceType` אם יש כלי
- `None` אם תא ריק ('.')

**קורא:**
- ✅ `click()` - זיהוי הכלי שנבחר
- ✅ `_flush_actions()` - זיהוי כלים בהתנגשויות

**דוגמה:**
```python
pt = engine._piece_type(0, 0)  # קבל את הכלי ב-(0,0)
if pt:
    print(pt.code)  # 'N' - Knight
    print(pt.speed_ms)  # 3000 - איטי
```

---

### **2. `_is_moving(r, c)`**

```python
def _is_moving(r, c) -> bool:
    """בדוק אם הכלי במיקום (r, c) כרגע בדרך (תנועה רגילה)."""
```

**מטרה:** וידוא שכלי לא בתנועה לפני הזזה חדשה.

**חוזר:**
- `True` אם יש Action פעיל עם `start=(r,c)` ו-`is_jump=False`
- `False` אחרת

**קורא:**
- ✅ `click()` - בדיקה שלא ניתן להזיז כלי בתנועה
- ✅ `jump()` - בדיקה שלא ניתן לקפוץ עם תנועה פעילה

**דוגמה:**
```python
if engine._is_moving(0, 0):
    print("רוק עדיין בדרך!")
```

---

### **3. `_is_airborne(r, c)`**

```python
def _is_airborne(r, c) -> bool:
    """בדוק אם הכלי במיקום (r, c) כרגע קופץ."""
```

**מטרה:** וידוא שכלי לא קופץ לפני קפיצה חדשה.

**חוזר:**
- `True` אם יש Action פעיל עם `start=(r,c)` ו-`is_jump=True`
- `False` אחרת

**קורא:**
- ✅ `click()` - מניעת תנועה תוך כדי קפיצה
- ✅ `jump()` - מניעת קפיצה כפולה

**דוגמה:**
```python
if engine._is_airborne(1, 1):
    print("כלי כבר בקפיצה!")
```

---

### **4. `_is_destination_taken(tr, tc)`**

```python
def _is_destination_taken(tr, tc) -> bool:
    """בדוק אם היעד (tr, tc) כבר שמור על ידי כלי אחר."""
```

**מטרה:** מניעת התנגשות - שני כלים לא יכולים להגיע לאותה משבצת.

**חוזר:**
- `True` אם יש Action פעיל עם `end=(tr,tc)` ו-`is_jump=False`
- `False` אחרת

**הערה:** רק תנועות רגילות חוסמות (לא קפיצות - הן "באויר").

**קורא:**
- ✅ `click()` - בדיקה שלא ניתן לנוע ליעד שעוד כלי צפוי שם

**דוגמה:**
```python
# Robot1 נע ל-(2,1), Robot2 מנסה גם לנוע ל-(2,1)
if engine._is_destination_taken(2, 1):
    print("כלי אחר כבר בדרך לשם!")
```

---

### **5. `_route_conflicts(start, end)`**

```python
def _route_conflicts(start, end) -> bool:
    """בדוק אם יש כלי אחר שנע לאותה עמודה מאותו כיוון."""
```

**מטרה:** מניעת צפיפות בעמודה - כלים לא יכולים להיות "זה אחרי זה" באותה עמודה.

**כלל:**
- אם שניי כלים נעים לאותה **עמודה (col)** מאותו **כיוון (left→right או right→left)**
- זה conflict!

**לא** מחסום head-to-head (כלים הולכים זה כנגד זה - זה בסדר).

**קורא:**
- ✅ `click()` - בדיקה אחרונה לפני ביצוע תנועה

**דוגמה:**
```python
# Piece A: (0,0) → (0,3)  [עמודה 0 → 3, כיוון ימינה]
# Piece B: (0,1) → (0,3)  [עמודה 0 → 3, כיוון ימינה]
# ❌ CONFLICT! לא ניתן להזיז את B

# אבל:
# Piece A: (0,0) → (0,3)  [ימינה]
# Piece C: (0,3) → (0,0)  [שמאלה]
# ✅ OK! head-to-head, יוכרעו לפי עדיפות
```

---

### **6. `_travel_time(start, end, piece_type)`**

```python
def _travel_time(start, end, piece_type) -> int:
    """חשב את זמן התנועה (milliseconds) עבור כלי מסוג מסוים."""
```

**מטרה:** קביעת משך התנועה לפי סוג הכלי.

**חוזר:** משך בmill seconds מ-`PieceRegistry.MOVE_DURATION_MS`

**מרווחים:**
- King: 1000ms (חשוב להגנה)
- Queen/Rook/Bishop: 2000ms (כבדים)
- Knight: 3000ms (האיטי ביותר - כי קופץ)
- Pawn: 500ms (הקל ביותר)

**קורא:**
- ✅ `click()` - חישוב משך התנועה החדשה

**דוגמה:**
```python
knight_type = PieceRegistry.get('N')
duration = engine._travel_time((0,0), (2,1), knight_type)
# duration = 3000ms
```

---

## ⚡ Main Methods (Public)

### **7. `_flush_actions()` - ⭐ הליבה!**

```python
def _flush_actions():
    """
    פתרון כל הפעולות שהסתיימו בזמן הנוכחי.
    זו הפונקציה החשובה ביותר - כאן קורה כל המשחק!
    """
```

**זרימה:**
1. **אסיפה:** איזה פעולות סיימו (end_time <= current_time)
2. **מיון:** לפי start_time (כדי להשמר סדר)
3. **Head-to-Head Detection:** זהה כלים המחליפים משבצות
4. **Jump Resolution:** קפיצות תופסות מגיעים
5. **Normal Moves:** תנועות רגילות עם לכידות
6. **Promotion:** קידום חיילים ל-Queen

**פעילויות מפורטות:**

#### **שלב 1: Head-to-Head**
```
אם A nע ל-B.start ו-B נע ל-A.start (חיצויים):
- המוביל (start_time קטן) ניצח
- המפסיד מוסר מ-board
```

#### **שלב 2: Jumps Capture**
```
אם כלי קופץ במיקומו ו-כלי אחר מגיע אליו:
- הקופץ אוכל את המגיע (כלי מוסר בנקודת המוצא שלו)
- הקופץ מקבל נקודות
```

#### **שלב 3: Normal Moves**
```
תנועות רגילות - הכלי נע למשבצת אחרת:
- אם כלי בהגעה, הוא נלכד
- נקודות מוענקות לשחקן
```

#### **שלב 4: Pawn Promotion**
```
אם חייל הגיע לשורה האחרונה:
- הוא מתקדם ל-Queen
```

**קורא:**
- ✅ `click()` - בתחילה (לפני בחירה חדשה)
- ✅ `wait()` - אחרי הגדלת זמן

**דוגמה:**
```python
engine.wait(3000)  # המתן 3 שניות
# _flush_actions() נקראת אוטומטית
# כל הפעולות עם end_time <= 3000 יבוצעו
```

---

### **8. `click(x, y)` - 🎯 קלט ראשוני**

```python
def click(x, y):
    """טופל בקליק של השחקן על הלוח."""
```

**זרימה:**
1. בדוק אם המשחק הסתיים
2. המר pixels ל-grid coords: `row = y // 100, col = x // 100`
3. בדוק אם בתוך גבולות
4. flush actions קודמות
5. אם לא נבחר כלי - בחר
6. אם נבחר כלי - בדוק חוקיות וביצע

**בדיקות חוקיות:**
- ✅ `is_legal_move()` - תנועה חוקית לפי כללי סוג הכלי
- ✅ `is_path_blocked()` - נתיב פנוי (משלא Jumper)
- ✅ `_is_moving()` - כלי לא בתנועה כרגע
- ✅ `_is_destination_taken()` - יעד לא שמור
- ✅ `_route_conflicts()` - אין חסימת עמודה

**אם חוקית:**
- יצור `Action` והוסף ל-queue

**קורא:**
- ✅ `runner.py` - בפקודה "click x y"

**דוגמה:**
```python
# קליק בפיקסל (50, 50) = (0, 0)
engine.click(50, 50)
engine.selected = (0, 0)  # בחר את הכלי ב-(0,0)

# קליק בפיקסל (150, 50) = (1, 0) - הזז שם
engine.click(150, 50)
# בדוק חוקיות...
# אם חוקי: Action((0,0), (1,0), 0, 1000) → queue
```

---

### **9. `jump(x, y)` - 🦘 קפיצה**

```python
def jump(x, y):
    """טופל בקפיצה הגנתית של השחקן."""
```

**מטרה:** מאפשרת לכלי "לקפוץ במקום" כדי להימנע מתקיפה.

**בדיקות:**
- ✅ לא ריק
- ✅ לא בתנועה כרגע
- ✅ לא כבר בקפיצה

**אם תקף:**
- יצור `Action` עם `start == end`
- משך: `JUMP_DURATION_MS` (1000ms)

**קורא:**
- ✅ `runner.py` - בפקודה "jump x y"

**דוגמה:**
```python
# קליק בפיקסל (50, 50) = (0, 0)
engine.jump(50, 50)
# Action((0,0), (0,0), current_time, 1000) → queue
# הכלי "קופץ למעלה" להימנע מתקיפה מגיעה
```

---

### **10. `wait(ms)` - ⏳ הליכת זמן**

```python
def wait(ms: int):
    """הליכת זמן - מקדמת את הסימולציה."""
```

**מטרה:** הליכת זמן הסימולציה כדי לאפשר לפעולות להתרחש.

**זרימה:**
1. בדוק אם המשחק הסתיים
2. הגדל את `current_time` ב-`ms`
3. קרא ל-`_flush_actions()` - הוא יבדוק אילו פעולות סיימו

**זה מה שגורם לתנועות להיות מעשית!**

**קורא:**
- ✅ `runner.py` - בפקודה "wait ms"

**דוגמה:**
```python
engine.wait(1500)
# current_time עלה ל-1500
# _flush_actions() תבדוק אילו Actions עם end_time <= 1500
# הם מבוצעים עכשיו
```

---

### **11. `is_game_over()`**

```python
def is_game_over() -> bool:
    """בדוק אם המשחק הסתיים - אחד המלכים נלכד."""
```

**סיום:** כשניקוד השחקן הוא `∞` (כלומר המלך נלכד).

**חוזר:**
- `True` אם `scores['w'] == inf` או `scores['b'] == inf`
- `False` אחרת

**קורא:**
- ✅ `click()` - בתחילה (מניעת משחק אחרי סוף)
- ✅ `jump()` - בתחילה
- ✅ `wait()` - בתחילה

**דוגמה:**
```python
if engine.is_game_over():
    print("המשחק הסתיים! תוצאה חד-משמעית!")
    return  # עצור כל פעולה חדשה
```

---

## 📊 Call Graph - מי קורא למי?

```
┌─ runner.py: click(x, y)
│   └─ GameEngine.click()
│       ├─ is_game_over()
│       ├─ _flush_actions()
│       │   ├─ _piece_type()
│       │   └─ [conflict logic]
│       ├─ _piece_type()
│       ├─ is_legal_move() [Board]
│       ├─ is_path_blocked() [Board]
│       ├─ _is_moving()
│       ├─ _is_destination_taken()
│       ├─ _route_conflicts()
│       └─ _travel_time()
│
├─ runner.py: jump(x, y)
│   └─ GameEngine.jump()
│       ├─ is_game_over()
│       ├─ _is_moving()
│       └─ _is_airborne()
│
└─ runner.py: wait(ms)
    └─ GameEngine.wait()
        ├─ is_game_over()
        └─ _flush_actions()
            ├─ _piece_type()
            ├─ move_piece() [Board]
            └─ [collision resolution]
```

---

## 🎯 Summary Table

| פונקציה | סוג | קריאה מ | מטרה |
|---------|------|---------|------|
| `_piece_type` | Private | click, _flush | זיהוי סוג כלי |
| `_is_moving` | Private | click, jump | בדיקה תנועה |
| `_is_airborne` | Private | click, jump | בדיקה קפיצה |
| `_is_destination_taken` | Private | click | בדיקה יעד תפוס |
| `_route_conflicts` | Private | click | בדיקה חסימה עמודה |
| `_travel_time` | Private | click | חישוב משך |
| `_flush_actions` | Private | click, wait | ⚡ ליבת המנוע |
| `click` | Public | runner | קלט - בחירה/תנועה |
| `jump` | Public | runner | קלט - קפיצה |
| `wait` | Public | runner | קלט - הליכת זמן |
| `is_game_over` | Public | click, jump, wait | בדיקה סיום |

---

## 💡 Key Insights

1. **Action Queue** - התנועות לא מתבצעות מיד, הן "בדרך" עד שה-time מתאים
2. **_flush_actions()** - הלב של המנוע, אחראית על כל פתרונות ההתנגשויות
3. **Validation Early** - בדיקות חוקיות ב-click מונעות בעיות מאוחר יותר
4. **Snapshot Pattern** - שימור מצב לוח לפני מוטציות עוזר בפתרון התנגשויות
5. **Score = ∞** - המלך בעל ערך אינסופי - תיו קבוע גמור את המשחק

---

**Version:** 1.0  
**Last Updated:** 2026-07-09  
**Owner:** Team
