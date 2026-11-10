#include <Arduino.h>
#include <NimBLEDevice.h>
#include <Preferences.h>
#include <esp_random.h>
#include <array>
#include <atomic>
#include <string>

namespace {
constexpr int buttonPin = 4;
constexpr uint32_t debounceMs = 45;
constexpr uint32_t pairHoldMs = 4000;
constexpr uint32_t pairWindowMs = 60000;
constexpr uint32_t noConnection = BLE_HS_CONN_HANDLE_NONE;
constexpr char serviceId[] = "a969ba54-806f-4d1b-b763-640c13563949";
constexpr char eventId[] = "a969ba55-806f-4d1b-b763-640c13563949";

NimBLEServer* server = nullptr;
NimBLECharacteristic* events = nullptr;
Preferences binding;
std::string trustedPeer;
std::atomic<uint32_t> peer{noConnection};
std::atomic<uint32_t> subscriber{noConnection};
std::atomic<uint32_t> pairingDeadline{0};
std::atomic<uint32_t> pairingCode{0};

bool pairingOpen() {
    const uint32_t until = pairingDeadline.load();
    return until != 0 && static_cast<int32_t>(until - millis()) > 0;
}

bool authenticated(const NimBLEConnInfo& info) {
    return info.isEncrypted() && info.isAuthenticated() && info.isBonded();
}

class LinkCallbacks final : public NimBLEServerCallbacks {
    void onConnect(NimBLEServer* link, NimBLEConnInfo& info) override {
        const auto address = info.getIdAddress();
        const bool trusted = address.toString() == trustedPeer && NimBLEDevice::isBonded(address);
        const uint32_t handle = info.getConnHandle();
        uint32_t empty = noConnection;
        if ((!pairingOpen() && !trusted) || !peer.compare_exchange_strong(empty, handle)) {
            link->disconnect(info.getConnHandle());
            return;
        }
        NimBLEDevice::startSecurity(info.getConnHandle());
    }

    void onDisconnect(NimBLEServer*, NimBLEConnInfo& info, int) override {
        uint32_t handle = info.getConnHandle();
        subscriber.compare_exchange_strong(handle, noConnection);
        handle = info.getConnHandle();
        peer.compare_exchange_strong(handle, noConnection);
    }

    uint32_t onPassKeyDisplay() override { return pairingCode.load(); }

    void onAuthenticationComplete(NimBLEConnInfo& info) override {
        const auto address = info.getIdAddress().toString();
        if (!authenticated(info) || peer.load() != info.getConnHandle() ||
            (address != trustedPeer && (!pairingOpen() || !binding.putString("controller", address.c_str())))) {
            server->disconnect(info.getConnHandle());
            return;
        }
        trustedPeer = address;
        pairingDeadline.store(0);
        pairingCode.store(0);
    }
} linkCallbacks;

class SubscriptionCallbacks final : public NimBLECharacteristicCallbacks {
    void onSubscribe(NimBLECharacteristic*, NimBLEConnInfo& info, uint16_t mode) override {
        uint32_t handle = info.getConnHandle();
        if (mode == 2 && handle == peer.load() && authenticated(info) && info.getIdAddress().toString() == trustedPeer) {
            subscriber.store(handle);
        } else {
            subscriber.compare_exchange_strong(handle, noConnection);
        }
    }
} subscriptionCallbacks;

void openPairingWindow() {
    if (peer.load() != noConnection) return;
    const uint32_t code = esp_random() % 1000000U;
    pairingCode.store(code);
    pairingDeadline.store(millis() + pairWindowMs);
    Serial.printf("Pair %s with passkey %06lu within 60 seconds.\n",
                  NimBLEDevice::getAddress().toString().c_str(), static_cast<unsigned long>(code));
}

void sendPress(uint16_t handle) {
    std::array<uint8_t, 17> frame{};
    frame[0] = 1;
    esp_fill_random(frame.data() + 1, frame.size() - 1);
    frame[7] = (frame[7] & 0x0F) | 0x40;
    frame[9] = (frame[9] & 0x3F) | 0x80;
    events->indicate(frame.data(), frame.size(), handle);
}
}  // namespace

void setup() {
    Serial.begin(115200);
    pinMode(buttonPin, INPUT_PULLUP);
    if (!binding.begin("help-button")) {
        Serial.println("Cannot open button configuration storage.");
        return;
    }
    trustedPeer = binding.getString("controller").c_str();
    if (!NimBLEDevice::init("NianNian Help")) {
        Serial.println("Cannot start BLE controller.");
        return;
    }
    NimBLEDevice::setSecurityIOCap(BLE_HS_IO_DISPLAY_ONLY);
    NimBLEDevice::setSecurityAuth(true, true, true);
    server = NimBLEDevice::createServer();
    server->setCallbacks(&linkCallbacks);
    auto* service = server->createService(serviceId);
    events = service->createCharacteristic(eventId, NIMBLE_PROPERTY::INDICATE | NIMBLE_PROPERTY::READ_AUTHEN);
    events->setCallbacks(&subscriptionCallbacks);
    service->start();

    auto* advertising = NimBLEDevice::getAdvertising();
    advertising->addServiceUUID(serviceId);
    NimBLEAdvertisementData response;
    response.setName("NianNian Help");
    advertising->setScanResponseData(response);
    advertising->enableScanResponse(true);
    server->advertiseOnDisconnect(true);
    advertising->start();
    Serial.println("Hold the external button for four seconds while disconnected to open pairing.");
}

void loop() {
    static int raw = HIGH;
    static int stable = HIGH;
    static uint32_t lastEdge = 0;
    static uint32_t pressedAt = 0;
    static bool handled = false;
    if (events == nullptr) {
        delay(250);
        return;
    }

    const uint32_t now = millis();
    const int level = digitalRead(buttonPin);
    if (level != raw) {
        raw = level;
        lastEdge = now;
    }
    if (raw != stable && now - lastEdge >= debounceMs) {
        stable = raw;
        if (stable == LOW) {
            pressedAt = now;
            const uint32_t handle = subscriber.load();
            handled = handle != noConnection;
            if (handled) sendPress(static_cast<uint16_t>(handle));
        }
    }
    if (stable == LOW && !handled && now - pressedAt >= pairHoldMs) {
        handled = true;
        openPairingWindow();
    }
    delay(8);
}
