"""RAG 检索引擎：基于 TF-IDF + 余弦相似度，离线可用，中文兼容"""
import base64
import json
import re
from typing import List, Dict, Tuple

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..database import SessionLocal
from ..models import DocumentChunk, Document


def _split_text(text: str, chunk_size: int = 500, overlap: int = 100) -> List[str]:
    """递归字符切片：按段落/句子/字符递归切分"""
    if not text or not text.strip():
        return []
    # 按段落切分
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: List[str] = []
    buf = ""
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        if len(buf) + len(para) <= chunk_size:
            buf = (buf + "\n" + para).strip()
        else:
            if buf:
                chunks.append(buf)
            # 段落过长则按句子切分
            if len(para) > chunk_size:
                sentences = re.split(r"(?<=[。！？!?\n.])", para)
                buf = ""
                for s in sentences:
                    s = s.strip()
                    if not s:
                        continue
                    if len(buf) + len(s) <= chunk_size:
                        buf = (buf + s).strip()
                    else:
                        if buf:
                            chunks.append(buf)
                        buf = s
            else:
                buf = para
    if buf:
        chunks.append(buf)

    # 添加重叠
    if overlap > 0 and len(chunks) > 1:
        overlapped = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_tail = chunks[i - 1][-overlap:] if len(chunks[i - 1]) > overlap else chunks[i - 1]
            overlapped.append(prev_tail + chunks[i])
        chunks = overlapped
    return chunks


class RAGService:
    def __init__(self):
        # 字符级 1-2 gram，兼容中英文
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(1, 2),
            max_features=20000,
            sublinear_tf=True,
        )
        self._fitted = False
        self._chunk_vectors: Dict[int, np.ndarray] = {}  # chunk_id -> vector
        self._chunk_texts: Dict[int, str] = {}
        self._all_texts: List[str] = []
        self._all_ids: List[int] = []

    def _ensure_fitted(self):
        """首次使用时从数据库加载已有切片并拟合 vectorizer"""
        if self._fitted:
            return
        db = SessionLocal()
        try:
            chunks = db.query(DocumentChunk).all()
            if chunks:
                texts = [c.content for c in chunks]
                self.vectorizer.fit(texts)
                for c in chunks:
                    vec = self.vectorizer.transform([c.content])
                    self._chunk_vectors[c.id] = vec.toarray()[0]
                    self._chunk_texts[c.id] = c.content
                    self._all_texts.append(c.content)
                    self._all_ids.append(c.id)
            else:
                # 用空语料初始化，避免未拟合报错
                self.vectorizer.fit(["初始化"])
            self._fitted = True
        finally:
            db.close()

    def add_document(self, doc_id: int, content: str, couple_id: int) -> int:
        """切片并向量化文档，返回切片数"""
        self._ensure_fitted()
        chunks_text = _split_text(content)
        if not chunks_text:
            return 0

        db = SessionLocal()
        try:
            # 重新拟合（增量：加入新文本）
            all_existing = list(self._chunk_texts.values()) + chunks_text
            self.vectorizer.fit(all_existing)
            # 重新计算已有向量
            for cid, ctext in self._chunk_texts.items():
                self._chunk_vectors[cid] = self.vectorizer.transform([ctext]).toarray()[0]

            count = 0
            for idx, ctext in enumerate(chunks_text):
                vec = self.vectorizer.transform([ctext]).toarray()[0]
                vec_b64 = base64.b64encode(vec.tobytes()).decode("ascii")
                chunk = DocumentChunk(
                    document_id=doc_id,
                    couple_id=couple_id,
                    chunk_index=idx,
                    content=ctext,
                    vector_b64=vec_b64,
                )
                db.add(chunk)
                db.flush()
                self._chunk_vectors[chunk.id] = vec
                self._chunk_texts[chunk.id] = ctext
                self._all_texts.append(ctext)
                self._all_ids.append(chunk.id)
                count += 1
            db.query(Document).filter(Document.id == doc_id).update({"chunk_count": count})
            db.commit()
            return count
        finally:
            db.close()

    def remove_document(self, doc_id: int):
        """删除文档及其切片索引"""
        db = SessionLocal()
        try:
            chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).all()
            for c in chunks:
                self._chunk_vectors.pop(c.id, None)
                self._chunk_texts.pop(c.id, None)
                if c.id in self._all_ids:
                    idx = self._all_ids.index(c.id)
                    self._all_ids.pop(idx)
                    self._all_texts.pop(idx)
            db.query(DocumentChunk).filter(DocumentChunk.document_id == doc_id).delete()
            db.commit()
        finally:
            db.close()

    def search(self, query: str, couple_id: int, top_k: int = 3) -> List[Dict]:
        """检索最相关的切片，返回带来源信息"""
        self._ensure_fitted()
        # 过滤当前情侣的切片
        db = SessionLocal()
        try:
            couple_chunks = db.query(DocumentChunk).filter(
                DocumentChunk.couple_id == couple_id
            ).all()
        finally:
            db.close()

        if not couple_chunks:
            return []

        candidate_ids = [c.id for c in couple_chunks]
        candidate_texts = [self._chunk_texts.get(c.id, c.content) for c in couple_chunks]

        # 对候选切片重新拟合查询向量
        try:
            query_vec = self.vectorizer.transform([query])
            # 用候选文本构建矩阵
            candidate_matrix = self.vectorizer.transform(candidate_texts)
            sims = cosine_similarity(query_vec, candidate_matrix)[0]
        except Exception:
            # vectorizer 未见过某些词，退化为关键词匹配
            sims = np.array([self._keyword_score(query, t) for t in candidate_texts])

        ranked = sorted(
            zip(candidate_ids, candidate_texts, sims),
            key=lambda x: x[2],
            reverse=True,
        )[:top_k]

        results = []
        for cid, text, score in ranked:
            if score > 0.01:
                # 找到所属文档名
                db = SessionLocal()
                try:
                    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == cid).first()
                    doc = db.query(Document).filter(Document.id == chunk.document_id).first() if chunk else None
                finally:
                    db.close()
                results.append({
                    "content": text,
                    "score": round(float(score), 4),
                    "source": doc.filename if doc else "未知文档",
                    "document_id": chunk.document_id if chunk else None,
                    "chunk_id": cid,
                })
        return results

    def _keyword_score(self, query: str, text: str) -> float:
        """关键词匹配得分（降级方案）"""
        q_chars = set(query)
        t_chars = set(text)
        if not q_chars:
            return 0.0
        return len(q_chars & t_chars) / len(q_chars) * 0.5


rag_service = RAGService()
