# Руководство по воспроизведению (№16)

## Требования

- Python 3.10+ (для CI фиксирована 3.11).
- Git; для некоторых моделей — NumPy, scikit-learn или PyTorch (установите по `requirements.txt`).
- Для бенчмарков C++ потребуются clang++/g++; для локальных HTTP-опытов — доступный localhost.

## Установка

```bash
git clone https://github.com/Shtenco/tiimeweb_synergy_exactly_once_delivery.git
cd tiimeweb_synergy_exactly_once_delivery
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## Запуск

```bash
python experiments/exactly_once_lab.py --out results/local --unique 20 --copies 2 --workers 2
```

> Выборки, предупреждения об обучении и зависимости конкретного сценария см. в исходниках. Полный запуск может требовать отдельных датасетов и дополнительной оперативной памяти.

## Что записать в протокол

- Версии Python и пакетов, git commit SHA, процессор и объём памяти.
- Выбранные параметры, seed, источник данных и правила разделения train/test.
- Результаты каждого повтора, необработанные логи, проверки корректности.
- Причины исключения любых прогонов. Не удаляйте неудачные попытки без объяснения.

## Проверка синтаксиса

```bash
python -m compileall -q prototypes experiments tests  # если каталоги существуют
```

CI проверяет компиляцию исходников и документы, не проводит оплачиваемых тестов LLM/GPU или production-нагрузку.
