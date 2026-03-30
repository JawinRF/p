package com.prismshield

import android.app.Application

class PrismApp : Application() {
    override fun onCreate() {
        super.onCreate()
        // Warm up the DB on app start so first query isn't slow
        MemShieldDb.get(this)
    }
}
