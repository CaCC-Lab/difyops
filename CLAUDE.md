# Claude Code 指示書

## コーディング規約

- Python 3.10+
- 型ヒント必須
- docstring必須（Google style）

## ディレクトリ構造

- 実装コード: `dify_admin/`
- テストコード: `tests/`
- ログ出力: `logs/`

## 禁止事項

- `print()` の使用（stderr への出力は可）
- 外部APIキーのハードコード
- bare except（`except Exception` は可）
