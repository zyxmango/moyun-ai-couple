"""可复现的离线检索评估：输出 Recall@3、MRR 与平均延迟。"""
import tempfile
from pathlib import Path
from time import perf_counter

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import SharedMemory
from app.services.memory_service import memory_service


MEMORIES = [
    ("m01", "重庆旅行", "第一次去重庆，在洪崖洞看夜景，还吃了小面。"),
    ("m02", "生日礼物", "去年生日收到一台拍立得相机作为礼物。"),
    ("m03", "周末电影", "商量好这个周六下午一起去看科幻电影。"),
    ("m04", "饮食偏好", "小墨喜欢清淡的粤菜，最近胃不舒服需要少辣。"),
    ("m05", "咖啡习惯", "小韵喝拿铁不加糖，更喜欢安静有窗的位置。"),
    ("m06", "成都计划", "计划明年春天去成都，在人民公园喝茶。"),
    ("m07", "第一次约会", "第一次正式约会是在江边散步，之后吃了火锅。"),
    ("m08", "纪念日", "每年五月二十日是确定关系的纪念日。"),
    ("m09", "雨天备选", "下雨时更愿意在家一起做饭或者看老电影。"),
    ("m10", "宠物愿望", "两个人都想以后领养一只橘猫，名字叫年糕。"),
    ("m11", "运动偏好", "周末喜欢骑行，但不喜欢强度很高的爬山。"),
    ("m12", "海边日出", "在厦门旅行时一起早起去黄厝海滩看日出。"),
    ("m13", "甜品偏好", "喜欢抹茶和芝士蛋糕，不爱太甜的奶油。"),
    ("m14", "音乐节", "去年秋天一起参加了草莓音乐节，最喜欢傍晚场。"),
    ("m15", "预算习惯", "平时约会希望控制在两人三百元以内，把钱留给旅行。"),
    ("m16", "手作体验", "一起做过陶艺杯，觉得协作类手作很有意思。"),
    ("m17", "周年照片", "两周年在植物园拍了一组胶片风格照片。"),
    ("m18", "晚餐禁忌", "小韵不吃香菜，对花生轻微过敏。"),
    ("m19", "读书约会", "喜欢在书店各自选一本书，再交换阅读感受。"),
    ("m20", "露营想法", "想尝试一次轻量露营，但希望营地有洗手间和电源。"),
]

CASES = [
    ("我们第一次去重庆看了哪里的夜景", "m01"),
    ("生日送过什么摄影相关的东西", "m02"),
    ("这个周六安排了什么活动", "m03"),
    ("最近吃饭为什么要少放辣椒", "m04"),
    ("喝咖啡时想坐什么位置", "m05"),
    ("明年春天准备去哪座城市", "m06"),
    ("最早那次正式约会做了什么", "m07"),
    ("我们确定关系的日子是哪天", "m08"),
    ("下雨不能出门可以一起干嘛", "m09"),
    ("以后想养什么宠物", "m10"),
    ("不喜欢哪种高强度户外活动", "m11"),
    ("在厦门哪里看过日出", "m12"),
    ("甜点更偏爱什么口味", "m13"),
    ("去年秋天参加了哪个音乐活动", "m14"),
    ("平常两个人约会预算多少", "m15"),
    ("之前共同做过什么手工", "m16"),
    ("两周年照片在哪里拍的", "m17"),
    ("晚餐需要避开什么食材", "m18"),
    ("适合安静交流的阅读约会是什么", "m19"),
    ("露营地点需要具备哪些设施", "m20"),
]


def baseline_search(question: str, top_k: int = 3):
    """对照组：只使用字符 TF-IDF，不加入业务排序信号。"""
    corpus = [f"{title} {content}" for _, title, content in MEMORIES]
    vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 3), sublinear_tf=True)
    matrix = vectorizer.fit_transform(corpus + [question])
    scores = cosine_similarity(matrix[-1], matrix[:-1])[0]
    ranked = scores.argsort()[::-1][:top_k]
    return [MEMORIES[index][0] for index in ranked]


def evaluate(name, search):
    hits = 0
    reciprocal_rank = 0.0
    elapsed_ms = 0.0
    failures = []
    for question, expected_id in CASES:
        started = perf_counter()
        ids = search(question)
        elapsed_ms += (perf_counter() - started) * 1000
        rank = ids.index(expected_id) + 1 if expected_id in ids else 0
        hits += int(rank > 0)
        reciprocal_rank += 1 / rank if rank else 0
        if not rank:
            failures.append(question)
    total = len(CASES)
    result = {
        "name": name,
        "recall": hits / total,
        "mrr": reciprocal_rank / total,
        "latency": elapsed_ms / total,
        "failures": failures,
    }
    return result


def main():
    with tempfile.TemporaryDirectory() as directory:
        engine = create_engine(f"sqlite:///{(Path(directory) / 'eval.db').as_posix()}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
        db = Session()
        db.add_all([
            SharedMemory(
                couple_id=1,
                source_type="fixture",
                source_id=source_id,
                title=title,
                content=content,
                status="confirmed",
                visibility="shared",
                is_active=True,
            )
            for source_id, title, content in MEMORIES
        ])
        db.commit()

        results = [
            evaluate("纯字符 TF-IDF", baseline_search),
            evaluate(
                "混合排序",
                lambda question: [
                    item["source_id"]
                    for item in memory_service.search(db, 1, question, top_k=3, user_id=1)
                ],
            ),
        ]
        print("方案 | Recall@3 | MRR | 平均延迟")
        for result in results:
            print(
                f"{result['name']} | {result['recall']:.2%} | "
                f"{result['mrr']:.4f} | {result['latency']:.2f} ms"
            )
            for failure in result["failures"]:
                print(f"  MISS: {failure}")
        db.close()
        engine.dispose()


if __name__ == "__main__":
    main()
