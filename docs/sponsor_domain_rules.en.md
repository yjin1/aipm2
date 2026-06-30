# Sponsor Domain Rules from PDF #2

**Source PDF:** `docs/2-AIPM工程管理フロー抽出_20260430.pdf`

## Executable Precedence Rules

- `仕様 -> 基本設計`
- `基本設計 -> 承認`
- `承認 -> 出図`
- `出図 -> 銅帯図`
- `枠組 -> パネル`
- `枠組 -> 塗装`
- `塗装 -> 組立枠組器具付`
- `組立枠組器具付 -> 配線`
- `配線 -> チェック仕上`
- `チェック仕上 -> 検査`
- `検査 -> 立会受検`
- `立会受検 -> 完成`
- `完成 -> 出荷`

## Executable Temporal Lag Rules

| Rule | Scheduler Meaning |
|---|---|
| Panel start is two days after frame start | `panel_start >= frame_start + 2 days` |
| Panel finish is 0-8 hours after frame finish | `frame_finish <= panel_finish <= frame_finish + 8 hours` |

## Advisory Knowledge

- Oracle-D6 interface automation
- Resource calendars and alternative resource groups
- Reference-pattern selection checks
- Due-date-change and related-ship logic
- Inspection alignment across related products
- Witness inspection time windows
- Special paint-color batching
- Delivery transport periods
- Outsourcing supplier selection

