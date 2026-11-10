import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

// La chiave API di Drive sta in local.properties, fuori dal repository:
// CHAMETIGER_DRIVE_API_KEY=... Senza, l'app funziona coi soli file copiati via USB.
val locali = Properties().apply {
    rootProject.file("local.properties").takeIf { it.isFile }?.inputStream()?.use { load(it) }
}

android {
    namespace = "io.github.sirfrederik.chametiger"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "io.github.sirfrederik.chametiger"
        minSdk = 26
        targetSdk = 37
        versionCode = 2
        versionName = "1.1"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"

        buildConfigField("String", "DRIVE_API_KEY", "\"${locali.getProperty("CHAMETIGER_DRIVE_API_KEY", "").trim()}\"")
    }

    // La firma di debug uguale su tutti i PC: Google confronta lo SHA-1 del
    // certificato con la restrizione della chiave API, e Android rifiuta un
    // aggiornamento firmato con un'altra chiave. In local.properties, con le
    // barre in avanti: CHAMETIGER_KEYSTORE=G:/Il mio Drive/.../debug.keystore
    // Senza, vale il debug.keystore di questo PC.
    signingConfigs {
        getByName("debug") {
            locali.getProperty("CHAMETIGER_KEYSTORE")?.trim()?.takeIf { it.isNotEmpty() }?.let { percorso ->
                val keystore = file(percorso)
                if (!keystore.isFile) {
                    throw GradleException(
                        "CHAMETIGER_KEYSTORE in local.properties punta a $keystore, che non c'e'. " +
                            "Drive e' montato? Per usare la firma di questo PC, togli la riga."
                    )
                }
                storeFile = keystore
                storePassword = "android"
                keyAlias = "androiddebugkey"
                keyPassword = "android"
            }
        }
    }

    buildTypes {
        release {
            optimization {
                enable = true
                packageScope = setOf("androidx.**", "kotlin.**", "kotlinx.**")
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(project(":motore"))
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.work.runtime.ktx)
    implementation(libs.kotlinx.serialization.json)
    testImplementation(libs.junit)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
}