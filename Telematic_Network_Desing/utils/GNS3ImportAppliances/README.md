# GNS3 Import Appliances

## Instalación de Appliances

- La carpeta `applicances` contiene todas las imágenes que serán importadas de la siguiente manera, usando la del enrutador `cisco-3725` como muestra:

1. Se Copie/Descargue en el host donde corre el cliente GNS3 la imagen correspondiente al dispositivo. Todas las appliances se ubican en `~/TelematicsNetworkDesign/utils/appliances`.

2. Después, en el cliente GNS3, vamos a *File*, *Import appliance*, se localiza el directorio donde se tiene la *imágen descargada* y *Abrir*.

3. Seleccionar instalar el dispositivo en el servidor principal:

    <img src="./img/1.PNG"  width="60%" height="30%">

4. Seleccionar la imagen del dispositivo:

    <img src="./img/2.PNG"  width="60%" height="30%">

    > **Nota:** Si la imagen del dispositivo no es encontrada se debe a que previamente no ha sido cargada en el servidor GNS3. En  ese caso siga las siguientes [instrucciones](../GNS3MissingImages/README.md).
    >> **Importante:** Regrese a este apartado al cargar la imagen necesaria.

5. Aceptar la instalación de la imagen del dispositivo:

    <img src="./img/3.PNG"  width="60%" height="30%">

6. Terminar el proceso de instalación de la imagen del dispositivo:

    <img src="./img/4.PNG"  width="60%" height="30%">

7. Recibir mensaje de imagen del dispositivo instalada:

    <img src="./img/5.PNG"  width="60%" height="30%">