# Driftmate — OpenCode Context

Driftmate, upstream dependency drift tespiti yapan ve isteğe bağlı olarak insan onaylı remediation akışına kadar ilerleyebilen açık kaynak bir CLI aracıdır. Dockerfile, Helm chart ve Terraform bağımlılıklarını cluster'a bağlanmadan analiz eder; gerektiğinde GitHub ve Telegram entegrasyonlarıyla yönlendirilmiş remediation sürecini destekler.

## Architecture Rules

- `core/` hiçbir zaman `providers/`, `channels/` veya `build/` altındaki adapter modüllerini import etmez.
- Bağımlılık yönü her zaman adapter → core şeklinde kalmalıdır.
- Bu izolasyon kuralı her değişiklikte korunmalıdır.

## Verification

- `pytest`
- `mypy src/driftmate`
