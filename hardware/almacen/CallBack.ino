//Esta función se ejecuta al recepcionar un mensaje al que esté subscrito el dispositivo
void callback(char* topic, byte* payload, unsigned int length) 
{
  #ifdef DEBUG
  Serial.print("Ha llegado un mensaje [");
  Serial.print(topic);
  Serial.print("] ");
  for (int i = 0; i < length; i++) 
  {
    Serial.print((char)payload[i]);
  }
  Serial.println();
  #endif
}