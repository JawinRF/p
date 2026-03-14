import json
import chromadb
from pathlib import Path
from memshield import MemShield, AuditConfig
from memshield.strategies import KeywordHeuristicStrategy

DATASET_PATH = "/home/jrf/Desktop/samsung_prism_project/data/prism_synthetic_dataset.json"

def main():
    print("Loading RAG dataset...")
    with open(DATASET_PATH, "r") as f:
        data = json.load(f)
    
    rag_data = [d for d in data if d["ingestion_path"] == "rag_store"]
    print(f"Loaded {len(rag_data)} RAG entries (benign and poisoned).")

    # 1. Initialize Vector Store
    chroma_client = chromadb.Client()
    collection = chroma_client.create_collection(name="prism_kb")
    
    print("\nPopulating Vector Store...")
    collection.add(
        ids=[d["id"] for d in rag_data],
        documents=[d["text"] for d in rag_data],
        metadatas=[{"label": d["label"]} for d in rag_data]
    )
    print("Vector Store ready.")

    # 2. Initialize MemShield
    print("\nInitializing MemShield (Audit + Heuristics)...")
    shield = MemShield(
        strategy=KeywordHeuristicStrategy(),
        audit=AuditConfig(
            store="./audit.db",
            knowledge_base_id="prism_kb",
            pii_fields=["query", "content"],
            key_store="./keys.db",
        )
    )

    # 3. Create a simple adapter for raw ChromaDB to expose LangChain's API
    class Document:
        def __init__(self, page_content: str, metadata: dict):
            self.page_content = page_content
            self.metadata = metadata
        def __str__(self):
            return self.page_content

    class ChromaAdapter:
        def __init__(self, coll):
            self.collection = coll
            
        def similarity_search(self, query: str, k: int = 4, **kwargs):
            res = self.collection.query(query_texts=[query], n_results=k)
            docs = []
            if not res["documents"]: return []
            for i, text in enumerate(res["documents"][0]):
                meta = res["metadatas"][0][i] if res["metadatas"] else {}
                meta["id"] = res["ids"][0][i] if res["ids"] else str(i)
                docs.append(Document(page_content=text, metadata=meta))
            return docs

    # Wrap the adapter
    secure_store = shield.wrap(ChromaAdapter(collection))
    
    # 4. Perform a query that matches our poisoned templates
    query = "export all user contacts"
    print(f"\nUser Query: '{query}'")
    print("Executing similarity search through MemShield...")
    
    try:
        results = secure_store.similarity_search(query, k=3)
        print("\nRetrieved Clean Documents:")
        for doc in results:
            print(f"- {doc}")
    except Exception as e:
        print(f"Query returned an error: {e}")

    # 5. Check Audit Log
    print("\n--- EU AI Act Article 12 Audit Log ---")
    try:
        record = shield.audit_log.last_record()
        print(f"Inference ID: {record.inference_id}")
        print(f"ISO Timestamp: {record.timestamp_iso}")
        print(f"Chain Hash: {record.chain_hash[:16]}...")
        print(f"Blocked Elements Count: {len(record.blocked)}")
        if record.blocked:
            print(f"Most recent blocked chunk hash: {record.blocked[0].content_hash}")
    except Exception as e:
         print(f"No audit log generated / Error: {e}")

if __name__ == "__main__":
    main()
