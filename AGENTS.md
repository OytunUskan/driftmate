# Driftmate — OpenCode Context

Driftmate, upstream dependency drift tespiti yapan ve isteğe bağlı olarak insan onaylı remediation akışına kadar ilerleyebilen açık kaynak bir CLI aracıdır. Dockerfile, Helm chart ve Terraform bağımlılıklarını cluster'a bağlanmadan analiz eder; gerektiğinde GitHub ve Telegram entegrasyonlarıyla yönlendirilmiş remediation sürecini destekler.

## Architecture Rules

- `core/` hiçbir zaman `providers/`, `channels/` veya `build/` altındaki adapter modüllerini import etmez.
- Bağımlılık yönü her zaman adapter → core şeklinde kalmalıdır.
- Bu izolasyon kuralı her değişiklikte korunmalıdır.

## Workflow Rules

- PLAN MODE sonrası: `plan-review` OTOMATİK çalıştırılır — kullanıcı ayrıca “review et” demek zorunda değildir. Bu, her plan çalıştırmasının standart, ayrılmaz bir parçasıdır.
- BUILD MODE sonrası: `code-review` OTOMATİK çalıştırılır — aynı şekilde, ayrıca istenmesine gerek yoktur.
- Her `plan-review` veya `code-review` sonunun EN SONUNA, aşağıdaki formatta bir özet bloğu eklenir:

  ```markdown
  ## Özet (Claude için)
  - Ne yapıldı: [1-2 cümle]
  - Doğrulama sonucu: [tek satır]
  - Değişen dosyalar: [liste, sadece dosya adları]
  - Commit: [hash + mesaj, varsa; yoksa "yok"]
  - Dikkat edilmesi gereken/şüpheli bir durum var mı: [varsa 1 cümle, yoksa "yok"]
  ```

  Bu özet, review’un kendi ham çıktısının EN SONUNA eklenir; ham çıktının yerine geçmez. Kullanıcı isterse ham çıktıya da bakabilir, fakat varsayılan olarak bu özet Claude’a iletilir.

## Verification

- `pytest`
- `mypy src/driftmate`
