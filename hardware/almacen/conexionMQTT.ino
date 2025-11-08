void reconexion() 
{

  //Ejecuta mientras no esté reconectado
  while (!client.connected()) 
  { 
    #ifdef DEBUG
    Serial.print("Esperando conexion MQTT...");
    #endif
    
    // Intentar conectar
    // if (client.connect(clientId.c_str(), mqttUser, mqttPassword)) 
    if (client.connect(clientId, mqttUser, mqttPassword))
    {
      #ifdef DEBUG
      Serial.println("Conectado");
      #endif
      char mensaje[40];

      snprintf(mensaje, sizeof(mensaje), "El %s se ha conectado", clientId);      
      // sprintf(mensaje, "El %s se ha conectado", clientId);
      // Al conectarse publica un comentario al topic "sistema"
      client.publish("rfid/sistema", mensaje);
      // ... y se resuscribe al topic del dispositivo
      // char sub[16];
      // sprintf(sub, "recepcion/%s", clientId);
      // client.subscribe(sub);                    //Subscrito al topic recepcion/[almacen_x]
    } 
    else 
    {
      #ifdef DEBUG
      Serial.print("failed, rc=");
      Serial.print(client.state());
      Serial.println(" Intentalo de nuevo en 5 segundos");
      #endif
      //Espera 5 segundos antes de intentarlo de nuevo
      delay(5000);
    }
  }
}