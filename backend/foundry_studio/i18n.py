"""Backend-localized message catalog.

The API never hard-codes user-facing copy in one language.  Errors carry a
stable ``message_key`` plus optional ``params``; the frontend renders the
localized string for the active language (zh / en / ja / ru).  The backend
catalog below is used for server-side rendering (e.g. log lines) and as a
fallback when a key is unknown to the frontend.
"""

from __future__ import annotations

# message_key -> {locale: template}.  ``{param}`` placeholders are substituted.
MESSAGES: dict[str, dict[str, str]] = {
    "error.unknown": {
        "zh": "发生未知错误：{detail}",
        "en": "An unknown error occurred: {detail}",
        "ja": "不明なエラーが発生しました: {detail}",
        "ru": "Произошла неизвестная ошибка: {detail}",
    },
    "error.model_not_found": {
        "zh": "未知的模型：{model}",
        "en": "Unknown model: {model}",
        "ja": "不明なモデル: {model}",
        "ru": "Неизвестная модель: {model}",
    },
    "error.job_not_found": {
        "zh": "任务 {job_id} 不存在",
        "en": "Job {job_id} does not exist",
        "ja": "ジョブ {job_id} は存在しません",
        "ru": "Задача {job_id} не существует",
    },
    "error.invalid_params": {
        "zh": "任务参数无效：{detail}",
        "en": "Invalid job parameters: {detail}",
        "ja": "ジョブパラメータが無効です: {detail}",
        "ru": "Недопустимые параметры задачи: {detail}",
    },
    "error.no_input_files": {
        "zh": "模型 {model} 需要上传输入文件",
        "en": "Model {model} requires input file upload",
        "ja": "モデル {model} には入力ファイルが必要です",
        "ru": "Модель {model} требует загрузки входных файлов",
    },
    "error.checkpoint_missing": {
        "zh": "模型 {model} 的权重未安装。请在“环境”页面安装后重试。",
        "en": "Checkpoint for {model} is not installed. Install it on the Environment page and retry.",
        "ja": "モデル {model} の重みがインストールされていません。「環境」ページでインストールしてから再試行してください。",
        "ru": "Веса модели {model} не установлены. Установите их на странице «Окружение» и повторите попытку.",
    },
    "error.engine_unavailable": {
        "zh": "模型 {model} 的真实引擎不可用：{detail}",
        "en": "Real engine for {model} is unavailable: {detail}",
        "ja": "モデル {model} の実エンジンが利用できません: {detail}",
        "ru": "Реальный движок для {model} недоступен: {detail}",
    },
    "error.simulation_disabled": {
        "zh": "模拟模式已被禁用，且真实引擎不可用。",
        "en": "Simulation mode is disabled and the real engine is unavailable.",
        "ja": "シミュレーションモードが無効で、実エンジンが利用できません。",
        "ru": "Режим симуляции отключен, а реальный движок недоступен.",
    },
    "error.cancel_failed": {
        "zh": "任务 {job_id} 已结束，无法取消",
        "en": "Job {job_id} has already finished and cannot be canceled",
        "ja": "ジョブ {job_id} は終了しており、キャンセルできません",
        "ru": "Задача {job_id} уже завершена и не может быть отменена",
    },
    "error.file_not_found": {
        "zh": "文件不存在：{path}",
        "en": "File does not exist: {path}",
        "ja": "ファイルが存在しません: {path}",
        "ru": "Файл не существует: {path}",
    },
    "error.upload_failed": {
        "zh": "文件上传失败：{detail}",
        "en": "File upload failed: {detail}",
        "ja": "ファイルのアップロードに失敗しました: {detail}",
        "ru": "Не удалось загрузить файл: {detail}",
    },
    "error.invalid_file_type": {
        "zh": "不允许的文件类型：{filename}（允许：{allowed}）",
        "en": "File type not allowed: {filename} (allowed: {allowed})",
        "ja": "許可されていないファイルタイプです: {filename}（許可: {allowed}）",
        "ru": "Недопустимый тип файла: {filename} (разрешено: {allowed})",
    },
    "error.cannot_parse_params": {
        "zh": "无法解析参数 JSON：{detail}",
        "en": "Cannot parse parameters JSON: {detail}",
        "ja": "パラメータJSONを解析できません: {detail}",
        "ru": "Не удалось разобрать JSON параметров: {detail}",
    },
    "error.job_already_finished": {
        "zh": "任务 {job_id} 已结束，不能再提交或修改",
        "en": "Job {job_id} has already finished; it cannot be submitted or modified",
        "ja": "ジョブ {job_id} は終了しており、送信・変更できません",
        "ru": "Задача {job_id} уже завершена; её нельзя отправить или изменить",
    },
    "error.checkpoint_install_failed": {
        "zh": "权重 {name} 安装失败：{detail}",
        "en": "Failed to install checkpoint {name}: {detail}",
        "ja": "重み {name} のインストールに失敗しました: {detail}",
        "ru": "Не удалось установить веса {name}: {detail}",
    },
    "error.cleanup_failed": {
        "zh": "清理失败：{detail}",
        "en": "Cleanup failed: {detail}",
        "ja": "クリーンアップに失敗しました: {detail}",
        "ru": "Не удалось выполнить очистку: {detail}",
    },
    "info.simulation_mode": {
        "zh": "模拟模式：当前结果由内置模拟引擎生成，仅用于界面与流程验证，不代表真实预测。",
        "en": "Simulation mode: results are produced by the built-in simulation engine for UI/flow validation only, not real predictions.",
        "ja": "シミュレーションモード：結果は組み込みシミュレーションエンジンによるもので、UI・フロー検証専用であり、実際の予測ではありません。",
        "ru": "Режим симуляции: результаты получены встроенным симуляционным движком и предназначены только для проверки интерфейса и потока, а не являются реальными предсказаниями.",
    },
    "error.build_spec_failed": {
        "zh": "无法构建任务规格：{detail}",
        "en": "Failed to build job specification: {detail}",
        "ja": "ジョブ仕様の構築に失敗しました: {detail}",
        "ru": "Не удалось построить спецификацию задачи: {detail}",
    },
    "error.hpc_not_configured": {
        "zh": "超算后端未配置：{detail}",
        "en": "HPC backend is not configured: {detail}",
        "ja": "HPCバックエンドが設定されていません: {detail}",
        "ru": "Бэкенд HPC не настроен: {detail}",
    },
    "error.submit_failed": {
        "zh": "任务提交失败：{detail}",
        "en": "Job submission failed: {detail}",
        "ja": "ジョブの送信に失敗しました: {detail}",
        "ru": "Не удалось отправить задачу: {detail}",
    },
    "error.remote_failed": {
        "zh": "远程任务执行失败，请查看日志。",
        "en": "Remote job failed; see logs for details.",
        "ja": "リモートジョブが失敗しました。詳細はログを確認してください。",
        "ru": "Удалённая задача завершилась с ошибкой; подробности в журнале.",
    },
    "error.agent_cannot_parse": {
        "zh": "无法从指令中解析出可执行计划：{detail}",
        "en": "Could not parse an executable plan from the instruction: {detail}",
        "ja": "指示から実行可能な計画を解析できませんでした: {detail}",
        "ru": "Не удалось разобрать исполняемый план из инструкции: {detail}",
    },
}


def _format(template: str, params: dict[str, str] | None) -> str:
    if not params:
        return template
    out = template
    for key, value in params.items():
        out = out.replace("{" + key + "}", str(value))
    return out


def localize(
    key: str, locale: str = "en", params: dict[str, str] | None = None
) -> str:
    """Return the localized message for ``key``.

    Falls back zh -> en -> the raw key so callers always get a usable string.
    """
    entry = MESSAGES.get(key)
    if entry is None:
        return key
    template = entry.get(locale) or entry.get("zh") or entry.get("en") or key
    return _format(template, params)
