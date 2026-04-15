Got it — here is the **entire MD file in one single continuous block** for direct copy-paste:

````md
# Codex Handoff: Fully Asymmetric Draft Decision Engine (Context-Conditioned Pick Model)

## Objective

At pick time, compute:

V(c | S_t)

for each candidate champion c, given a partially revealed draft state, and return:

argmax_c V(c | S_t)

---

## 1. REQUIRED INPUT (must be provided before computation)

```json
{
  "player_role": "string",
  "player_champion_context": "string | null",

  "ally_faceup_champions": ["champion_id", "..."],
  "enemy_faceup_champions": ["champion_id", "..."],

  "candidate_champions": ["champion_id", "..."]
}
````

### Hard constraint

Do NOT compute any values unless:

* ally_faceup_champions is provided
* enemy_faceup_champions is provided
* candidate_champions is provided

---

## 2. CORE IDEA

We define:

V(c | S_t) = Σ A(c,a) + Σ E(c,e) + U(c)

Where:

* A(c,a) = ally synergy (enablement)
* E(c,e) = enemy pressure (counterplay)
* U(c) = optional future uncertainty term

No symmetry assumption:
A(c,a) ≠ -E(c,a)

---

## 3. ENEMY PRESSURE FUNCTION

E(c,e) models:

* lane disadvantage
* kill threat
* disruption
* tempo pressure

Example form:

E(c,e) = sigmoid(w1*lane_pressure + w2*burst + w3*macro_pressure)

---

## 4. ALLY SYNERGY FUNCTION

A(c,a) models:

* combo synergy
* peel/engage alignment
* scaling synergy

Example form:

A(c,a) = log(1 + (v1*combo + v2*teamfight + v3*scaling))

---

## 5. FUTURE UNCERTAINTY (OPTIONAL)

U(c) = expected impact of unseen picks

U(c) = Σ P(x | meta) * interaction(c, x)

---

## 6. FULL VALUE FUNCTION

V(c) =
Σ_{a ∈ A_t} A(c,a)

* Σ_{e ∈ E_t} E(c,e)
* U(c)

---

## 7. COMPUTATION FLOW

### Step 1: validate input

Ensure:

* ally_faceup_champions exists
* enemy_faceup_champions exists
* candidate_champions exists

### Step 2: compute scores

for each c in candidate_champions:
V(c) = 0

```
for a in ally_faceup_champions:
    V(c) += A(c,a)

for e in enemy_faceup_champions:
    V(c) += E(c,e)

V(c) += U(c)
```

### Step 3: rank

Return candidates sorted by V(c) descending

---

## 8. KEY PROPERTY

This system naturally handles:

* asymmetric n vs n+1 draft visibility
* sequential picks
* partial information states

No normalization required.

---

## 9. INTERPRETATION

Enemy side:

* pressure / punishment

Ally side:

* enablement / synergy

They are independent functions.

---

## 10. FINAL DECISION RULE

Pick = argmax_c V(c | S_t)

```

If you want, I can now turn this into a **fully executable Codex agent spec (with training data schema + inference API + learning loop for A/E functions)**.
```
