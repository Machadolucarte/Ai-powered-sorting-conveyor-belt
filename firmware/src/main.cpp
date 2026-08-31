#include <Servo.h> // 1. Inclui a biblioteca do Servo
#include <Arduino.h>

Servo meuServo;    // 2. Cria o objeto para controlar o servo

void setup() {
  Serial.begin(9600);
  meuServo.attach(9); // 3. Anexa o servo ao pino 9
}

void loop() {
  if (Serial.available()) {
    char cmd = Serial.read();
    
    if (cmd == 'S' || cmd == 's') { // Aceita 'S' maiúsculo ou minúsculo
      int angle = Serial.parseInt(); // Lê o número que vem depois do 'S'
      
      // 4. Limita o ângulo entre 0 e 180 graus por segurança
      angle = constrain(angle, 0, 180); 
      
      // 5. Move o servo para o ângulo desejado
      meuServo.write(angle); 
    }
  }
}
