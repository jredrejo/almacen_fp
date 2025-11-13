#include <Arduino.h>
#include "R200.h"

// Constructor
R200::R200(){};

bool R200::begin(HardwareSerial *serial, int baud, uint8_t RxPin, uint8_t TxPin) {
  _serial = serial;
  _serial->begin(baud, SERIAL_8N1, RxPin, TxPin);
  return true;
};

void printHexByte(char *name, uint8_t value) {
  Serial.print(name);
  Serial.print(":");
  Serial.print(value < 0x10 ? "0x0" : "0x");
  Serial.println(value, HEX);
}

void printHexBytes(char *name, uint8_t *value, uint8_t len) {
  Serial.print(name);
  Serial.print(":");
  Serial.print("0x");
  for (int i = 0; i < len; i++) {
    Serial.print(value[i] < 0x10 ? "0" : "");
    Serial.print(value[i], HEX);
  }
  Serial.println("");
}

void printHexWord(char *name, uint8_t MSB, uint8_t LSB) {
  Serial.print(name);
  Serial.print(":");
  Serial.print(MSB < 0x10 ? "0x0" : "0x");
  Serial.println(MSB, HEX);
  Serial.print(LSB < 0x10 ? "0" : "");
  Serial.println(LSB, HEX);
}

void R200::loop() {
  // Has any new data been received?
  if (dataAvailable()) {
    // Attempt to receive a full frame of data
    if (receiveData()) {
      if (dataIsValid()) {
        // If a full frame of data has been received, parse it
        switch (_buffer[R200_CommandPos]) {
          case CMD_GetModuleInfo:
            for (uint8_t i = 0; i < RX_BUFFER_LENGTH - 8; i++) {
              Serial.print((char)_buffer[6 + i]);
              // Stop when then only two bytes left are the CRC and FrameEnd marker
              if (_buffer[8 + i] == R200_FrameEnd) {
                break;
              }
            }
            Serial.println("");
            break;

          case CMD_SinglePollInstruction:
// Example successful response
// AA 02 22 00 11 C7 30 00 E2 80 68 90 00 00 50 0E 88 C6 A4 A7 11 9B 29 DD
// AA:Frame Header
// 02:Instruction Code
// 22:Command Parameter
// 00 11:Instruction data length (0x11 = 17 bytes)
// C7:RSSI Signal Strength
// 30 00: Label PC code (factory reg code)
// E2 80 68 90 00 00 50 0E 88 C6 A4 A7:EPC code
// 11 9B:CRC check
// 29: Verification
// DD: End of frame
#ifdef DEBUG
            printHexByte("RSSI", _buffer[5]);
            printHexWord("PC", _buffer[6], _buffer[7]);
            printHexBytes("EPC", &_buffer[8], 12);
#endif
            if (memcmp(uid, &_buffer[8], 12) != 0) {
              memcpy(uid, &_buffer[8], 12);
#ifdef DEBUG
              Serial.print("New card detected : ");
              dumpUIDToSerial();
              Serial.println("");
#endif
            } else {
#ifdef DEBUG
              Serial.print("Same card still present : ");
              dumpUIDToSerial();
              Serial.println("");
#endif
            }
#ifdef DEBUG
            printHexWord("CRC", _buffer[20], _buffer[21]);
#endif
            break;

          case CMD_ExecutionFailure:
            switch (_buffer[R200_ParamPos]) {
              case ERR_CommandError:
                Serial.println("Command error");
                break;
              case ERR_InventoryFail:
                // This is not necessarily a "failure" - it just means that there are no cards in range
                // Serial.print("No card detected!");
                // If there was previously a uid
                if (memcmp(uid, blankUid, sizeof uid) != 0) {
#ifdef DEBUG
                  Serial.print("Card removed : ");
                  dumpUIDToSerial();
                  Serial.println("");
#endif
                  memset(uid, 0, sizeof uid);
                }
                break;
              case ERR_AccessFail:
                // Serial.println("Access Fail");
                break;
              case ERR_ReadFail:
                // Serial.println("Read fail");
                break;
              case ERR_WriteFail:
                // Serial.println("Write fail");
                break;
              default:
                // Serial.print("Fail code ");
                // Serial.println(_buffer[R200_ParamPos], HEX);
                break;
            }
            break;
        }

        // Clear the buffer after successful processing
        // This prevents the same frame from being processed multiple times
        memset(_buffer, 0, RX_BUFFER_LENGTH);
      }
    }
  }
}

// Has any data been received from the reader?
bool R200::dataIsValid() {
#ifdef DEBUG
  Serial.println("Checking Data Valid");
  dumpReceiveBufferToSerial();
#endif
  uint8_t command = _buffer[2];
  // FF= no label return is received or data CRC verification error
  if (command == 255) { return false; }
  // NOTE
  // You can't just be smart and do this in one line, because
  // the pointer reference f*cks up.
  // uint16_t paramLength = _buffer[3]<<8 + _buffer[4];
  uint16_t paramLength = _buffer[3];
  paramLength <<= 8;
  paramLength += _buffer[4];
  uint8_t CRCpos = 5 + paramLength;

  // CRITICAL: Bounds check - prevent buffer overflow
  if (CRCpos >= RX_BUFFER_LENGTH) {
#ifdef DEBUG
    Serial.println("Error: CRC position out of bounds!");
#endif
    return false;
  }

  uint8_t CRC = calculateCheckSum(_buffer);
#ifdef DEBUG
  Serial.print("Calculated CRC: 0x");
  Serial.print(CRC, HEX);
  Serial.print(" | Received CRC: 0x");
  Serial.println(_buffer[CRCpos], HEX);
#endif
  return (CRC == _buffer[CRCpos]);
}

// Has any data been received from the reader?
bool R200::dataAvailable() {
  //Serial.println("Checking Data Available");
  return _serial->available() > 0;
}

/*
 * Dumps the most recently read UID to the serial output
 */
void R200::dumpUIDToSerial() {
  // Serial.print("Dumping UID...");
  Serial.print("0x");
  for (uint8_t i = 0; i < 12; i++) {
    Serial.print(uid[i] < 0x10 ? "0" : "");
    Serial.print(uid[i], HEX);
  }
  // Serial.println(". Done.");
}

void R200::dumpReceiveBufferToSerial() {
  // Serial.print("Dumping buffer...");
  Serial.print("0x");
  for (uint8_t i = 0; i < RX_BUFFER_LENGTH; i++) {
    Serial.print(_buffer[i] < 0x10 ? "0" : "");
    Serial.print(_buffer[i], HEX);
  }
  Serial.println(". Done.");
}

// Parse data that has been placed in the receive buffer
bool R200::parseReceivedData() {
  switch (_buffer[R200_CommandPos]) {
    case CMD_GetModuleInfo:
      break;
    case CMD_SinglePollInstruction:
      for (uint8_t i = 8; i < 20; i++) {
        uid[i - 8] = _buffer[i];
      };
      //memcpy(uid, _buffer+9, 12);
      break;
    case CMD_MultiplePollInstruction:
      for (uint8_t i = 8; i < 20; i++) {
        uid[i - 8] = _buffer[i];
      };
      //memcpy(uid, _buffer+9, 12);
      break;
    case CMD_ExecutionFailure:
      break;
    default:
      break;
  }
  return true;
}

/*
 * Note that Arduino Serial.flush() method does not clear the incoming serial buffer - only the outgoing!
 */
uint8_t R200::flush() {
  uint8_t bytesDiscarded = 0;
  while (_serial->available()) {
    _serial->read();
    bytesDiscarded++;
  }
  // Also clear our internal buffer
  memset(_buffer, 0, RX_BUFFER_LENGTH);
  return bytesDiscarded;
}

// Read incoming serial data sent by the reader
// This could either be a response to a command sent, or a notification
// (e.g. when set to automatic polling mode)
// Returns true if a complete frame of data is read within the allotted timeout
bool R200::receiveData(unsigned long timeOut) {
  unsigned long startTime = millis();
  uint8_t bytesReceived = 0;

  // Clear the buffer
  memset(_buffer, 0, RX_BUFFER_LENGTH);

  while ((millis() - startTime) < timeOut) {
    if (_serial->available()) {
      uint8_t b = _serial->read();

      if (bytesReceived > RX_BUFFER_LENGTH - 1) {
        // Buffer overflow - flush everything and start over
        Serial.print("Error: Max Buffer Length Exceeded!");
        flush();
        bytesReceived = 0;
        // Clear buffer again
        memset(_buffer, 0, RX_BUFFER_LENGTH);
        return false;
      } else {
        _buffer[bytesReceived] = b;
      }

      bytesReceived++;

      // Exit early once we have a complete frame
      // Check for frame end marker and ensure we have at least header + frame end
      if (b == R200_FrameEnd && bytesReceived >= 7) {
        // Verify frame starts with correct header
        if (_buffer[0] == R200_FrameHeader) {
          // Additional validation: verify paramLength matches frame size
          uint16_t paramLength = (_buffer[3] << 8) + _buffer[4];
          if (bytesReceived == (paramLength + 7)) {
            return true;  // Frame is complete, exit immediately
          }
        }
      }
    }
  }

  // Timeout reached
  if (bytesReceived > 0) {
    flush();
  }
  return false;
}

void R200::dumpModuleInfo() {
  uint8_t commandFrame[8] = { 0 };
  commandFrame[0] = R200_FrameHeader;
  commandFrame[1] = FrameType_Command;
  commandFrame[2] = CMD_GetModuleInfo;
  commandFrame[3] = 0x00;  // ParamLen MSB
  commandFrame[4] = 0x01;  // ParamLen LSB
  commandFrame[5] = 0x00;  // Param
  commandFrame[6] = 0x04;  // LSB of commandFrame[2] + commandFrame[3] + commandFrame[4] + commandFrame[5]
  commandFrame[7] = R200_FrameEnd;
  _serial->write(commandFrame, 8);
}

/**
 * Send single poll command to the reader
 */
void R200::poll() {
  uint8_t commandFrame[7] = { 0 };
  commandFrame[0] = R200_FrameHeader;
  commandFrame[1] = FrameType_Command;
  commandFrame[2] = CMD_SinglePollInstruction;
  commandFrame[3] = 0x00;  // ParamLen MSB
  commandFrame[4] = 0x00;  // ParamLen LSB
  commandFrame[5] = 0x22;  // Checksum
  commandFrame[6] = R200_FrameEnd;
  _serial->write(commandFrame, 7);
}

void R200::setMultiplePollingMode(bool enable) {
  if (enable) {
    uint8_t commandFrame[10] = { 0 };
    commandFrame[0] = R200_FrameHeader;
    commandFrame[1] = FrameType_Command;            //(0x00)
    commandFrame[2] = CMD_MultiplePollInstruction;  //0x27
    commandFrame[3] = 0x00;                         // ParamLen MSB
    commandFrame[4] = 0x03;                         // ParamLen LSB
    commandFrame[5] = 0x22;                         // Param (Reserved? Always 0x22 for this command)
    commandFrame[6] = 0xFF;                         // Param (Count of polls, MSB)
    commandFrame[7] = 0xFF;                         // Param (Count of polls, LSB)
    commandFrame[8] = 0x4A;                         // LSB of commandFrame[2] + commandFrame[3] + commandFrame[4] + commandFrame[5] + commandFrame[6] + commandFrame[7] (full value is 0x024A)
    commandFrame[9] = R200_FrameEnd;
    _serial->write(commandFrame, 10);
  } else {
    uint8_t commandFrame[7] = { 0 };
    commandFrame[0] = R200_FrameHeader;
    commandFrame[1] = FrameType_Command;     //(0x00)
    commandFrame[2] = CMD_StopMultiplePoll;  //0x28
    commandFrame[3] = 0x00;                  // ParamLen MSB
    commandFrame[4] = 0x00;                  // ParamLen LSB
    commandFrame[5] = 0x28;                  // LSB of commandFrame[2] + commandFrame[3] + commandFrame[4]
    commandFrame[6] = R200_FrameEnd;
    _serial->write(commandFrame, 7);
  }
}


/**
 * Get the current transmit power from the reader
 * Returns power in dBm (float)
 * Returns -1.0 if operation fails
 */
float R200::getPower() {
  flush();
  uint8_t commandFrame[7] = { 0 };
  commandFrame[0] = R200_FrameHeader;
  commandFrame[1] = FrameType_Command;
  commandFrame[2] = CMD_AcquireTransmitPower;
  commandFrame[3] = 0x00;  // ParamLen MSB
  commandFrame[4] = 0x00;  // ParamLen LSB
  commandFrame[5] = 0xB7;  // Checksum (0xB7 for this command)
  commandFrame[6] = R200_FrameEnd;

  _serial->write(commandFrame, 7);

    // Retry 3 times logic for reliability
  for (int attempt = 0; attempt < 3; attempt++) {
    if (receiveData(500)) {
      if (dataIsValid() && _buffer[R200_CommandPos] == CMD_AcquireTransmitPower) {
        // Response contains 2 bytes: MSB and LSB representing power * 100
        uint16_t powerValue = (_buffer[R200_ParamPos] << 8) | _buffer[R200_ParamPos + 1];
        return powerValue / 100.0;
      }
    }
  }
  return -1.0;
}

/**
 * Set the transmit power of the reader
 * power: float value in dBm (e.g., 20.5 for 20.5 dBm)
 * Returns true if successful, false otherwise
 * Note: tested modules only support values from 15 to 26 dBm
 */
bool R200::setPower(float power) {
  flush();
  // Convert float to integer (multiply by 100)
  uint16_t powerValue = (uint16_t)(power * 100);

  uint8_t commandFrame[9] = { 0 };
  commandFrame[0] = R200_FrameHeader;
  commandFrame[1] = FrameType_Command;
  commandFrame[2] = CMD_SetTransmitPower;
  commandFrame[3] = 0x00;                      // ParamLen MSB
  commandFrame[4] = 0x02;                      // ParamLen LSB (2 bytes for power value)
  commandFrame[5] = (powerValue >> 8) & 0xFF;  // MSB
  commandFrame[6] = powerValue & 0xFF;         // LSB

  // Calculate checksum: sum of type + command + param length MSB + param length LSB + params
  uint16_t checksum = FrameType_Command + CMD_SetTransmitPower + 0x00 + 0x02 + commandFrame[5] + commandFrame[6];
  commandFrame[7] = checksum & 0xFF;

  commandFrame[8] = R200_FrameEnd;

  _serial->write(commandFrame, 9);

  for (int attempt = 0; attempt < 3; attempt++) {
    if (receiveData(500)) {
      if (dataIsValid() && _buffer[R200_CommandPos] == CMD_SetTransmitPower) {
         // Check if response params contain [0] indicating success
        return (_buffer[R200_ParamPos] == 0);
      }
    }
  }

  return false;
}

/**
 * Get demodulator parameters from the reader
 * mixer_g: mixer gain
 * if_g: IF gain
 * thrd: signal demodulation threshold
 * Returns true if successful, false otherwise
 */
bool R200::getDemodulatorParams(uint8_t &mixer_g, uint8_t &if_g, uint16_t &thrd) {
  flush();
  uint8_t commandFrame[7] = { 0 };
  commandFrame[0] = R200_FrameHeader;
  commandFrame[1] = FrameType_Command;
  commandFrame[2] = CMD_GetReceiverDemodulatorParameters;
  commandFrame[3] = 0x00;  // ParamLen MSB
  commandFrame[4] = 0x00;  // ParamLen LSB
  commandFrame[5] = 0xF1;  // Checksum
  commandFrame[6] = R200_FrameEnd;

  _serial->write(commandFrame, 7);

  for (int attempt = 0; attempt < 3; attempt++) {
    if (receiveData(500)) {
      if (dataIsValid() && _buffer[R200_CommandPos] == CMD_GetReceiverDemodulatorParameters) {
        // Response format: [mixer_g] [if_g] [thrd_MSB] [thrd_LSB]
        mixer_g = _buffer[R200_ParamPos];
        if_g = _buffer[R200_ParamPos + 1];
        thrd = (_buffer[R200_ParamPos + 2] << 8) | _buffer[R200_ParamPos + 3];
        return true;
      }
    }
  }

  return false;
}

/**
 * Set demodulator parameters on the reader
 * mixer_g: mixer gain
 * if_g: IF gain
 * thrd: signal demodulation threshold
 * Returns true if successful, false otherwise
 */
bool R200::setDemodulatorParams(uint8_t mixer_g, uint8_t if_g, uint16_t thrd) {
  flush();
  uint8_t commandFrame[11] = { 0 };
  commandFrame[0] = R200_FrameHeader;
  commandFrame[1] = FrameType_Command;
  commandFrame[2] = CMD_SetReceiverDemodulatorParameters;
  commandFrame[3] = 0x00;  // ParamLen MSB
  commandFrame[4] = 0x04;  // ParamLen LSB (4 bytes: mixer_g, if_g, thrd_MSB, thrd_LSB)
  commandFrame[5] = mixer_g;
  commandFrame[6] = if_g;
  commandFrame[7] = (thrd >> 8) & 0xFF;  // thrd MSB
  commandFrame[8] = thrd & 0xFF;         // thrd LSB

  // Calculate checksum: sum of type + command + param length MSB + param length LSB + params
  uint16_t checksum = FrameType_Command + CMD_SetReceiverDemodulatorParameters + 0x00 + 0x04 + mixer_g + if_g + commandFrame[7] + commandFrame[8];
  commandFrame[9] = checksum & 0xFF;

  commandFrame[10] = R200_FrameEnd;

  _serial->write(commandFrame, 11);

  for (int attempt = 0; attempt < 3; attempt++) {
    if (receiveData(500)) {
      if (dataIsValid() && _buffer[R200_CommandPos] == CMD_SetReceiverDemodulatorParameters) {
        // Check if response params contain [0] indicating success
        return (_buffer[R200_ParamPos] == 0);
      }
    }
  }
  return false;
}


uint8_t R200::calculateCheckSum(uint8_t *buffer) {
  // Extract how many parameters there are in the buffer
  uint16_t paramLength = buffer[3];
  paramLength <<= 8;
  paramLength += buffer[4];

  // Checksum is calculated as the sum of all parameter bytes
  // added to four control bytes at the start (type, command, and the 2-byte parameter length)
  // Start from 1 to exclude frame header
  uint16_t check = 0;
  for (uint16_t i = 1; i < paramLength + 4 + 1; i++) {
    check += buffer[i];
  }
  // Now only return LSB
  return (check & 0xff);

  /*
  // This is an alternative checksum calculation sometimes used
  uint16_t paramLength = *(buffer+3);
  paramLength <<=8;
  paramLength += *(buffer+4);

  uint16_t sum = 0;
  for (int i=1; i<4+paramLength; i++) {
    sum += buffer[i];
  }
  return -sum;
  */
}

uint16_t R200::arrayToUint16(uint8_t *array) {
  uint16_t value = *array;
  value <<= 8;
  value += *(array + 1);
  return value;
}