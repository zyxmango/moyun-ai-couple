\set ON_ERROR_STOP on

BEGIN;

CREATE TABLE IF NOT EXISTS load_test_runs (
    name VARCHAR(100) PRIMARY KEY,
    couple_id INTEGER NOT NULL,
    message_count INTEGER NOT NULL,
    first_message_id INTEGER,
    last_message_id INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

WITH guard AS (
    SELECT NOT EXISTS (
        SELECT 1 FROM load_test_runs WHERE name = 'demo-chat-double-natural-v2'
    ) AS can_insert
),
ordered_times AS (
    SELECT created_at, row_number() OVER (ORDER BY id) AS row_number
    FROM messages
    WHERE couple_id = 1
),
source_rows AS (
    SELECT
        series.index,
        times.created_at,
        CASE
            WHEN series.index % 401 = 0 THEN format(
                '我们这次到了%s，先把行李放好再慢慢逛。',
                (ARRAY['武汉','重庆','南京','杭州','成都','厦门','青岛','苏州','长沙','西安','大理','泉州'])[
                    1 + ((series.index / 401)::integer % 12)
                ]
            )
            WHEN series.index % 401 = 1 THEN format(
                '下午去了%s，人不算多，我们拍了几张合照。',
                (ARRAY['东湖绿道','鹅岭二厂','颐和路','九溪','杜甫草堂','沙坡尾','小麦岛','虎丘','梅溪湖','西安城墙','喜洲古镇','蟳埔村'])[
                    1 + ((series.index / 401)::integer % 12)
                ]
            )
            WHEN series.index % 401 = 2 THEN format(
                '晚饭吃了%s，这家味道比预想中好。',
                (ARRAY['藕汤','重庆小面','盐水鸭','片儿川','甜水面','花生汤','鲅鱼水饺','桂花糖粥','米粉','甑糕','乳扇','四果汤'])[
                    1 + ((series.index / 401)::integer % 12)
                ]
            )
            WHEN series.index % 12 = 0 THEN format('今天%s，出门记得带%s。',
                (ARRAY['有点凉','太阳很好','下着小雨','风有点大','有些闷热','空气很清爽'])[1 + (series.index % 6)],
                (ARRAY['伞','薄外套','水杯','充电宝','门禁卡','耳机'])[1 + ((series.index / 7) % 6)])
            WHEN series.index % 12 = 1 THEN format('中午吃了%s，感觉比上周那家%s。',
                (ARRAY['鸡肉饭','馄饨','青菜面','番茄炒蛋','牛肉粉','饭团'])[1 + (series.index % 6)],
                (ARRAY['清淡一些','更香一点','更合口味','稍微咸一点','分量更足','更新鲜'])[1 + ((series.index / 11) % 6)])
            WHEN series.index % 12 = 2 THEN format('刚把%s处理完，我先起来走一走。',
                (ARRAY['周报','报表','会议记录','房间收纳','洗衣服','账单核对'])[1 + ((series.index / 5) % 6)])
            WHEN series.index % 12 = 3 THEN format('地铁现在%s，我大概%s到家。',
                (ARRAY['不太挤','有点慢','刚好有座位','临时限速','人比平时少'])[1 + (series.index % 5)],
                (ARRAY['六点四十','七点一刻','七点半','八点左右','八点二十'])[1 + ((series.index / 13) % 5)])
            WHEN series.index % 12 = 4 THEN format('快递放在%s了，取件码尾号是%s。',
                (ARRAY['门卫室','快递柜','前台','门口架子','便利店代收点'])[1 + (series.index % 5)],
                lpad(((series.index * 37) % 10000)::text, 4, '0'))
            WHEN series.index % 12 = 5 THEN format('冰箱里的%s还剩一点，晚上可以顺手解决掉。',
                (ARRAY['牛奶','生菜','蘑菇','鸡蛋','草莓','面包'])[1 + (series.index % 6)])
            WHEN series.index % 12 = 6 THEN format('今天工作节奏%s，不过事情都做完了。',
                (ARRAY['有点赶','很平稳','前紧后松','比昨天轻松','忙得很充实'])[1 + (series.index % 5)])
            WHEN series.index % 12 = 7 THEN format('刚听到一首%s，等会儿发给你。',
                (ARRAY['钢琴曲','老歌','轻爵士','民谣','电影配乐'])[1 + (series.index % 5)])
            WHEN series.index % 12 = 8 THEN format('晚上如果不累，我们下楼走%s分钟。', 15 + (series.index % 21))
            WHEN series.index % 12 = 9 THEN format('今天的云像%s，可惜没来得及拍清楚。',
                (ARRAY['一条鲸鱼','棉花糖','伸懒腰的猫','一座小岛','一片羽毛'])[1 + (series.index % 5)])
            WHEN series.index % 12 = 10 THEN format('手机还剩%s的电，我先找地方充一下。',
                (ARRAY['两成','三成','一半','六成'])[1 + (series.index % 4)])
            ELSE format('我刚看了一下时间，路口的灯还要等%s秒。', 8 + (series.index % 43))
        END AS content
    FROM generate_series(1, 80485) AS series(index)
    JOIN ordered_times AS times
      ON times.row_number = series.index
    CROSS JOIN guard
    WHERE guard.can_insert
),
inserted AS (
    INSERT INTO messages (couple_id, sender_id, content, msg_type, read_status, created_at)
    SELECT 1, CASE WHEN index % 2 = 0 THEN 1 ELSE 2 END, content, 'text', TRUE, created_at
    FROM source_rows
    ORDER BY index
    RETURNING id
)
INSERT INTO load_test_runs(name, couple_id, message_count, first_message_id, last_message_id)
SELECT 'demo-chat-double-natural-v2', 1, count(*), min(id), max(id)
FROM inserted
HAVING count(*) > 0;

UPDATE couple_ai_settings AS settings
SET last_synced_message_id = GREATEST(settings.last_synced_message_id, runs.last_message_id),
    sync_updated_at = CURRENT_TIMESTAMP,
    updated_at = CURRENT_TIMESTAMP
FROM load_test_runs AS runs
WHERE settings.couple_id = runs.couple_id
  AND runs.name = 'demo-chat-double-natural-v2';

COMMIT;

SELECT name, message_count, first_message_id, last_message_id, created_at
FROM load_test_runs
WHERE name = 'demo-chat-double-natural-v2';

SELECT couple_id, count(*) AS total_messages, min(created_at) AS first_chat, max(created_at) AS last_chat
FROM messages
WHERE couple_id = 1
GROUP BY couple_id;
