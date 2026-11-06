# ---- Проверка сайта GRAM Monitor (вставь в конец ~/scripts/monitor.sh) ----
SITE_FAIL=0

if systemctl is-active --quiet gram-monitor; then
    echo "✅ gram-monitor: сервис работает"
else
    echo "❌ gram-monitor: сервис НЕ работает"
    SITE_FAIL=1
fi

if systemctl is-active --quiet nginx; then
    echo "✅ nginx: работает"
else
    echo "❌ nginx: НЕ работает"
    SITE_FAIL=1
fi

# Проверяем сайт целиком, через nginx: /health отвечает 200, если курс свежий
HEALTH=$(curl -s -m 10 -o /dev/null -w '%{http_code}' http://127.0.0.1/health || true)
if [ "$HEALTH" = "200" ]; then
    echo "✅ сайт: /health = 200, курс свежий"
else
    echo "❌ сайт: /health = ${HEALTH:-нет ответа}"
    SITE_FAIL=1
fi

if [ "$SITE_FAIL" -ne 0 ]; then
    echo "⚠️  ВНИМАНИЕ: с сайтом GRAM проблемы! Смотри: journalctl -u gram-monitor -n 50"
    exit 1
fi
