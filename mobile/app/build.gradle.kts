plugins {
    id("com.android.application") version "9.4.1"
}

android {
    namespace = "ru.systemmonitor.mobile"
    compileSdk = 37

    defaultConfig {
        applicationId = "ru.systemmonitor.mobile"
        minSdk = 33
        targetSdk = 36
        versionCode = 1
        versionName = "1.0"
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}
