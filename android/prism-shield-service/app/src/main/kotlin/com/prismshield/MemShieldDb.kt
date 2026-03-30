package com.prismshield

import android.content.Context
import androidx.room.*

// ── Entities ─────────────────────────────────────────────────────────────────

@Entity(tableName = "memory_chunks")
data class MemoryChunk(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val source: String,         // "document", "note", "email", etc.
    val content: String,
    val embedding: String,      // JSON-serialised float array (simple cosine search)
    val insertedAt: Long = System.currentTimeMillis(),
    val scanVerdict: String = "PENDING"   // ALLOW | BLOCK | PENDING
)

@Entity(tableName = "audit_log")
data class AuditEntry(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val path: String,           // ingestion path: notification, clipboard, rag, etc.
    val snippet: String,        // first 120 chars of content
    val verdict: String,        // ALLOW | BLOCK
    val layer1Score: Float,
    val layer2Prob: Float,
    val matchedRules: String,   // comma-separated
    val timestamp: Long = System.currentTimeMillis()
)

// ── DAOs ─────────────────────────────────────────────────────────────────────

@Dao
interface MemoryChunkDao {
    @Insert
    suspend fun insert(chunk: MemoryChunk): Long

    @Query("SELECT * FROM memory_chunks WHERE scanVerdict = 'ALLOW' ORDER BY insertedAt DESC LIMIT 50")
    suspend fun getCleanChunks(): List<MemoryChunk>

    @Query("UPDATE memory_chunks SET scanVerdict = :verdict WHERE id = :id")
    suspend fun updateVerdict(id: Long, verdict: String)

    @Query("SELECT * FROM memory_chunks WHERE scanVerdict = 'PENDING'")
    suspend fun getPendingChunks(): List<MemoryChunk>

    @Query("DELETE FROM memory_chunks WHERE scanVerdict = 'BLOCK'")
    suspend fun deletePoisoned()
}

@Dao
interface AuditDao {
    @Insert
    suspend fun insert(entry: AuditEntry)

    @Query("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 200")
    suspend fun getRecent(): List<AuditEntry>

    @Query("SELECT COUNT(*) FROM audit_log WHERE verdict = 'BLOCK'")
    suspend fun blockedCount(): Int
}

// ── Database ──────────────────────────────────────────────────────────────────

@Database(
    entities = [MemoryChunk::class, AuditEntry::class],
    version  = 1,
    exportSchema = false
)
abstract class MemShieldDb : RoomDatabase() {
    abstract fun chunkDao(): MemoryChunkDao
    abstract fun auditDao(): AuditDao

    companion object {
        @Volatile private var INSTANCE: MemShieldDb? = null

        fun get(context: Context): MemShieldDb =
            INSTANCE ?: synchronized(this) {
                INSTANCE ?: Room.databaseBuilder(
                    context.applicationContext,
                    MemShieldDb::class.java,
                    "memshield.db"
                ).build().also { INSTANCE = it }
            }
    }
}

// ── MemShield Scanner ────────────────────────────────────────────────────────

/**
 * Called by the HTTP sidecar when OpenClaw queries its RAG store.
 *
 * Flow:
 *   Agent query → RAG retrieves N chunks → MemShield.scanChunks()
 *   → returns only ALLOW chunks → agent assembles prompt
 */
class MemShield(private val context: Context) {

    private val db by lazy { MemShieldDb.get(context) }

    /**
     * Store a new chunk (e.g. after document indexing).
     * Scans immediately; BLOCK chunks are stored but flagged.
     */
    suspend fun storeChunk(source: String, content: String, embedding: FloatArray): Long {
        val l1 = PrismDetector.scan(content)
        val verdict = if (l1.verdict == PrismDetector.Verdict.BLOCK) "BLOCK" else "ALLOW"

        return db.chunkDao().insert(
            MemoryChunk(
                source      = source,
                content     = content,
                embedding   = embedding.joinToString(","),
                scanVerdict = verdict
            )
        )
    }

    /**
     * Called at retrieval time. Scans chunks again (catches delayed detection).
     * Returns only ALLOW chunks — poison is silently dropped.
     */
    suspend fun scanChunks(chunks: List<MemoryChunk>): List<MemoryChunk> {
        return chunks.filter { chunk ->
            val l1 = PrismDetector.scan(chunk.content)
            if (l1.verdict == PrismDetector.Verdict.BLOCK) {
                db.chunkDao().updateVerdict(chunk.id, "BLOCK")
                db.auditDao().insert(
                    AuditEntry(
                        path         = "rag_retrieval",
                        snippet      = chunk.content.take(120),
                        verdict      = "BLOCK",
                        layer1Score  = l1.score,
                        layer2Prob   = 0f,
                        matchedRules = l1.matchedRules.joinToString(",")
                    )
                )
                false
            } else true
        }
    }

    /** Nightly cleanup of poisoned chunks */
    suspend fun purgePoison() = db.chunkDao().deletePoisoned()
}
