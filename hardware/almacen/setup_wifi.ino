void setup_wifi() 
{
  delay(10);
  // Nos conectamos a una red WiFi
  #ifdef DEBUG
  Serial.println();
  Serial.print("Conectandose a: ");
  Serial.println(ssid);
  #endif

  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) 
  {
    delay(500);
    #ifdef DEBUG
    Serial.print(".");
    #endif
  }

  randomSeed(micros());

  #ifdef DEBUG
  Serial.println("");
  Serial.println("WiFi conectada");
  Serial.println("Direccion IP: ");
  Serial.println(WiFi.localIP());
  #endif
}